import os
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import httpx
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from groq import Groq

app = FastAPI(title="DailyBrief API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
WEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
NEWS_COUNTRY = "IN"
GOOGLE_NEWS_HL = "en-IN"
GOOGLE_NEWS_CEID = "IN:en"

# ── Tool implementations ──────────────────────────────────────────────────────

def get_weather(city: str) -> dict:
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        r = httpx.get(url, timeout=8)
        data = r.json()
        if r.status_code != 200:
            return {"error": f"Could not fetch weather for {city}"}
        return {
            "city": data["name"],
            "temp_c": round(data["main"]["temp"]),
            "feels_like_c": round(data["main"]["feels_like"]),
            "condition": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "wind_kph": round(data["wind"]["speed"] * 3.6),
        }
    except Exception as e:
        return {"error": str(e)}


def search_news(topic: str, count: int = 3) -> dict:
    try:
        encoded_topic = urllib.parse.quote(topic)
        url = (
            "https://news.google.com/rss/search?q="
            f"{encoded_topic}%20when%3A1d&hl={GOOGLE_NEWS_HL}&gl={NEWS_COUNTRY}&ceid={GOOGLE_NEWS_CEID}"
        )
        r = httpx.get(url, timeout=8, follow_redirects=True)
        r.raise_for_status()

        root = ET.fromstring(r.text)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []

        articles = []
        for item in items[:count]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "Google News") if source_el is not None else "Google News"
            pub_date = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            articles.append({
                "title": title,
                "source": source,
                "url": link,
                "published": pub_date[:16] if pub_date else "",
            })

        return {"topic": topic, "articles": articles, "source": "google_news_rss", "country": NEWS_COUNTRY}
    except Exception as e:
        return {"error": str(e)}


def get_day_context(date_str: str = None) -> dict:
    now = datetime.now()
    weekday = now.strftime("%A")
    is_weekend = weekday in ("Saturday", "Sunday")
    return {
        "date": now.strftime("%B %d, %Y"),
        "weekday": weekday,
        "is_weekend": is_weekend,
        "time_of_day": "morning",
        "week_number": now.isocalendar()[1],
    }


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. 'Ahmedabad'"}
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search for recent news articles on a topic",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search news for"},
                    "count": {"type": "integer", "description": "Number of articles (1-3)", "default": 3},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_day_context",
            "description": "Get today's date, weekday, and context",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Optional date string"}
                },
            },
        },
    },
]

TOOL_MAP = {
    "get_weather": get_weather,
    "search_news": search_news,
    "get_day_context": get_day_context,
}


BAD_BRIEF_PHRASES = [
    "briefly summarize the three articles",
    "leo tolstoy",
    "wordpress",
    "swappable batteries",
    "digitalx agencies",
    "today's news in a nutshell",
    "game-changer",
    "must-have",
    "in a nutshell",
    "productized",
]


def _clean_brief_text(text: str) -> str:
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip().strip('"')
        lower = line.lower()

        if not line:
            cleaned_lines.append("")
            continue

        if any(phrase in lower for phrase in BAD_BRIEF_PHRASES):
            continue

        if line.startswith("[") and line.endswith("]"):
            continue

        cleaned_lines.append(line)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()
    return cleaned


def _needs_rewrite(text: str) -> bool:
    lower = text.lower()
    if any(phrase in lower for phrase in BAD_BRIEF_PHRASES):
        return True

    bullet_lines = [line for line in text.splitlines() if line.lstrip().startswith(("-", "*"))]
    if len(bullet_lines) < 3:
        return True

    if "thought for the day" not in lower:
        return True

    if "[" in text or "]" in text:
        return True

    return False


def _fallback_brief(req) -> str:
    focus = req.focus_today.strip() or "your top priority"
    city = req.city.strip() or "your city"
    return (
        f"Good morning from {city}.\n\n"
        f"- Start with {focus} before the day gets noisy.\n"
        f"- Skim the headlines, then keep only the items that actually change your next move.\n"
        f"- Leave the rest; momentum beats information overload.\n\n"
        f"Thought for the day: Keep it simple, keep it moving."
    )


def _assemble_brief_from_tools(req, messages) -> str:
    # Extract latest tool results for weather and each interest
    weather = None
    topic_articles = {}
    for m in messages:
        if m.get("role") == "tool":
            try:
                content = json.loads(m.get("content") or "{}")
            except Exception:
                continue
            # Heuristic: weather result contains 'temp_c' or 'condition'
            if isinstance(content, dict) and ("temp_c" in content or "condition" in content):
                weather = content
            # news articles stored as {'topic':..., 'articles':[...]} from search_news
            if isinstance(content, dict) and content.get("topic") and content.get("articles"):
                topic_articles[content["topic"]] = content.get("articles", [])

    # Greeting
    city = req.city or "your city"
    if weather and weather.get("temp_c") is not None:
        greeting = f"Good morning — {city} is {weather['temp_c']}°C and {weather.get('condition','clear')}."
    else:
        greeting = f"Good morning — here's your quick brief for {city}."

    # Build up to 3 bullets: one per interest if possible
    bullets = []
    for topic in req.interests[:3]:
        arts = topic_articles.get(topic) or []
        if arts:
            a = arts[0]
            title = a.get("title", "(no headline)")
            src = a.get("source", "source")
            date = a.get("published", "")
            bullets.append(f"- {topic.title()}: {title} — {src} {date}".strip())
        else:
            bullets.append(f"- {topic.title()}: no major updates found this morning.")

    # pad to 3 bullets
    while len(bullets) < 3:
        bullets.append("- No further updates.")

    if not any(line.startswith("-") and "no major updates" not in line.lower() for line in bullets):
        return ""

    thought = f"Thought for the day: Focus on {req.focus_today or 'one clear outcome'} and ship."

    assembled = "\n".join([greeting, "", *bullets, "", thought])
    return assembled


def _rewrite_brief(req, user_message: str, draft: str, messages) -> str:
    tool_notes = []
    for message in messages:
        if message.get("role") == "tool":
            tool_notes.append(message.get("content", ""))

    rewrite_prompt = (
        "Rewrite the draft into a clean, useful morning brief. "
        "Use the user's city, interests, focus, and the tool results only. "
        "Remove anything unrelated, dramatic, or invented. "
        "Never include literary quotes, placeholders, product pitches, generic investment advice, or article-summary stubs. "
        "Output only the final brief in plain text.\n\n"
        "Required format:\n"
        "- One short greeting line tied to the day or weather.\n"
        "- 3 concise bullet points grouped by the user's interests.\n"
        "- One short thought for the day that is practical and original.\n"
        "- Keep it under 220 words.\n\n"
        f"User message: {user_message}\n\n"
        f"Tool results: {json.dumps(tool_notes, ensure_ascii=False)}\n\n"
        f"Draft to rewrite: {draft}"
    )

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You rewrite brief copy with strict constraints and no fluff."},
            {"role": "user", "content": rewrite_prompt},
        ],
        max_tokens=450,
        temperature=0.2,
    )

    rewritten = response.choices[0].message.content or draft
    rewritten = _clean_brief_text(rewritten)
    return rewritten if rewritten else _fallback_brief(req)


def _has_news_content(text: str, interests: list[str]) -> bool:
    lower = text.lower()
    return any(topic.lower() in lower for topic in interests)


# ── Request model ─────────────────────────────────────────────────────────────

class BriefRequest(BaseModel):
    city: str
    interests: list[str]
    focus_today: str = ""


# ── Agentic streaming endpoint ────────────────────────────────────────────────

@app.post("/brief")
async def generate_brief(req: BriefRequest):
    interests_str = ", ".join(req.interests)
    system_prompt = (
        "You are a sharp, warm morning briefing agent. "
        "Use the available tools to gather context, then write a personalized morning brief. "
        "The news scope is India only. Use India-only news results and do not mention other regions. "
        "You MUST do this exactly:\n"
        "1. Call get_day_context first.\n"
        "2. Call get_weather with the user's city.\n"
        "3. Call search_news once for each interest, up to 3 total, using India-only news.\n"
        "4. After tool calls finish, write the final brief.\n\n"
        "Hard rules:\n"
        "- Use only facts from the tools and user input. Do not invent products, quotes, or side topics.\n"
        "- Never output placeholders like '[briefly summarize the three articles]'.\n"
        "- Never include literary quotes, generic investment tips, or random startup ads.\n"
        "- Keep it practical, specific, and friendly.\n"
        "- Keep the final answer under 220 words.\n\n"
        "Required format:\n"
        "- One short greeting line tied to the day or weather.\n"
        "- Exactly 3 concise bullets, one per interest, using the news results.\n"
        "- One short thought for the day that is original and relevant.\n"
        "- Tone: warm, direct, lightly witty, never robotic.\n"
        "- Never use the word 'delve'."
    )

    user_message = (
        f"My city: {req.city}. "
        f"My interests: {interests_str}. "
        f"What I'm focused on today: {req.focus_today or 'general productivity'}. "
        "Please run your tools and give me my morning brief."
    )

    messages = [{"role": "user", "content": user_message}]

    async def stream():
        # Agent loop — max 8 iterations to stay within free tier limits
        for _ in range(8):
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "system", "content": system_prompt}] + messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=800,
                temperature=0.3,
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # Stream tool calls as trace events
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    raw_args = tc.function.arguments or "{}"
                    try:
                        fn_args = json.loads(raw_args)
                    except Exception:
                        fn_args = {}

                    if not isinstance(fn_args, dict):
                        fn_args = {}

                    # Send trace event to frontend
                    trace = json.dumps({
                        "type": "tool_call",
                        "tool": fn_name,
                        "args": fn_args,
                    })
                    yield f"data: {trace}\n\n"

                    # Execute the tool
                    tool = TOOL_MAP.get(fn_name)
                    if tool is None:
                        result = {"error": f"Unknown tool: {fn_name}"}
                    else:
                        try:
                            result = tool(**fn_args)
                        except TypeError:
                            result = tool()

                    # Send result trace
                    result_trace = json.dumps({
                        "type": "tool_result",
                        "tool": fn_name,
                        "result": result,
                    })
                    yield f"data: {result_trace}\n\n"

                    # Add to message history
                    messages.append({"role": "assistant", "content": None, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": fn_name, "arguments": tc.function.arguments},
                        }
                    ]})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })

            # Final text response
            if finish_reason == "stop" and msg.content:
                final_text = _clean_brief_text(msg.content)
                assembled = _assemble_brief_from_tools(req, messages)
                if assembled:
                    final_text = assembled
                elif _needs_rewrite(final_text):
                    final_text = _rewrite_brief(req, user_message, final_text, messages)

                if _needs_rewrite(final_text) or not _has_news_content(final_text, req.interests):
                    final_text = _fallback_brief(req)

                final = json.dumps({"type": "brief", "content": final_text})
                yield f"data: {final}\n\n"
                yield "data: {\"type\": \"done\"}\n\n"
                return

            # If no tool calls and no content, something went wrong
            if not msg.tool_calls and not msg.content:
                yield "data: {\"type\": \"error\", \"message\": \"Agent produced no output\"}\n\n"
                return

        yield "data: {\"type\": \"error\", \"message\": \"Agent loop limit reached\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
