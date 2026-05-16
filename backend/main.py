import os
import json
import httpx
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

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
        url = (
            f"https://newsapi.org/v2/everything?q={topic}"
            f"&sortBy=publishedAt&pageSize={count}&language=en&apiKey={NEWS_API_KEY}"
        )
        r = httpx.get(url, timeout=8)
        data = r.json()
        if data.get("status") != "ok":
            return {"error": "News fetch failed", "details": data.get("message")}
        articles = [
            {
                "title": a["title"],
                "source": a["source"]["name"],
                "url": a["url"],
                "published": a["publishedAt"][:10],
            }
            for a in data.get("articles", [])[:count]
            if a.get("title") and "[Removed]" not in a.get("title", "")
        ]
        return {"topic": topic, "articles": articles}
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
        "Your job: use the available tools to gather context, then write a personalized morning brief. "
        "Steps you MUST follow:\n"
        "1. Call get_day_context to know what day it is.\n"
        "2. Call get_weather with the user's city.\n"
        "3. Call search_news for EACH of the user's interests (one call per topic, max 3 topics).\n"
        "4. After all tool calls are done, write the final brief.\n\n"
        "Final brief format:\n"
        "- Start with a one-line greeting referencing the day and weather mood.\n"
        "- 3-5 news bullets, grouped by topic, written like a smart friend summarizing — not a headline bot.\n"
        "- End with one short 'thought for the day' relevant to what they're focused on.\n"
        "- Tone: warm, direct, a little witty. Never robotic. Never use the word 'delve'.\n"
        "- Keep the whole brief under 300 words."
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
                temperature=0.7,
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # Stream tool calls as trace events
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)

                    # Send trace event to frontend
                    trace = json.dumps({
                        "type": "tool_call",
                        "tool": fn_name,
                        "args": fn_args,
                    })
                    yield f"data: {trace}\n\n"

                    # Execute the tool
                    result = TOOL_MAP[fn_name](**fn_args)

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
                final = json.dumps({"type": "brief", "content": msg.content})
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
