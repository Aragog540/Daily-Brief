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
USE_OPEN_METEO = os.environ.get("USE_OPEN_METEO", "false").lower() in ("1", "true", "yes")
NEWS_COUNTRY = "IN"
GOOGLE_NEWS_HL = "en-IN"
GOOGLE_NEWS_CEID = "IN:en"

# ── Tool implementations ──────────────────────────────────────────────────────

def get_weather(city: str) -> dict:
    # Enhanced weather: prefer Open-Meteo when configured, otherwise use OpenWeather One Call
    try:
        # Prefer Open-Meteo (no API key) when requested
        if USE_OPEN_METEO:
            # Geocode via Open-Meteo's geocoding API (no key required)
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
            g = httpx.get(geo_url, timeout=8)
            g.raise_for_status()
            geoj = g.json() or {}
            results = geoj.get("results", [])
            if not results:
                return {"error": f"Could not geocode {city}"}
            lat = results[0]["latitude"]
            lon = results[0]["longitude"]
            name = results[0].get("name", city)

            # Call Open-Meteo forecast
            om_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto"
            )
            om = httpx.get(om_url, timeout=8)
            om.raise_for_status()
            omd = om.json()
            daily = omd.get("daily", {})
            maxs = daily.get("temperature_2m_max", [])
            mins = daily.get("temperature_2m_min", [])
            pops = daily.get("precipitation_probability_max", [])
            max_temp = round(maxs[0]) if maxs else None
            min_temp = round(mins[0]) if mins else None
            pop = pops[0] / 100.0 if pops else None

            summary_parts = []
            if max_temp is not None and min_temp is not None:
                if max_temp >= 42:
                    summary_parts.append(f"expected to be extremely hot today, with temperatures around {max_temp}°C during the day and about {min_temp}°C at night")
                else:
                    summary_parts.append(f"expected to reach around {max_temp}°C with lows near {min_temp}°C")

            if pop is not None:
                if pop >= 0.5:
                    summary_parts.append("with a good chance of rain today")
                elif pop >= 0.2:
                    summary_parts.append("with some chance of showers")
                else:
                    summary_parts.append("with very little chance of rain")

            summary = ", ".join(summary_parts).strip().capitalize() + "."
            advice = ["Stay hydrated", "Use light clothing and sunscreen"]
            if max_temp and max_temp >= 40:
                advice = ["Avoid direct sun between 12 PM – 4 PM", "Stay hydrated", "Use light cotton clothes and sunscreen", "Limit strenuous outdoor activity"]

            return {
                "city": name,
                "temp_c": None,
                "feels_like_c": None,
                "condition": "",
                "humidity": None,
                "wind_kph": None,
                "max_temp_c": max_temp,
                "min_temp_c": min_temp,
                "day_condition": "",
                "summary": summary,
                "advice": advice,
            }

        # Otherwise use OpenWeather (requires API key)
        if not WEATHER_API_KEY:
            return {"error": "OPENWEATHER_API_KEY not set"}

        # 1) geocode city to lat/lon via OpenWeather
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={urllib.parse.quote(city)}&limit=1&appid={WEATHER_API_KEY}"
        g = httpx.get(geo_url, timeout=8)
        g.raise_for_status()
        geo = g.json() or []
        if not geo:
            return {"error": f"Could not geocode {city}"}
        lat = geo[0]["lat"]
        lon = geo[0]["lon"]
        name = geo[0].get("name", city)

        # 2) onecall for daily forecast
        one_url = (
            f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}"
            f"&exclude=minutely,hourly,alerts&units=metric&appid={WEATHER_API_KEY}"
        )
        o = httpx.get(one_url, timeout=8)
        o.raise_for_status()
        od = o.json()

        current = od.get("current", {})
        daily = od.get("daily", [])
        today = daily[0] if daily else {}

        temp_now = round(current.get("temp")) if current.get("temp") is not None else None
        feels = round(current.get("feels_like")) if current.get("feels_like") is not None else None
        cond = (current.get("weather") or [{}])[0].get("description", "")

        max_temp = round(today.get("temp", {}).get("max")) if today.get("temp") else None
        min_temp = round(today.get("temp", {}).get("min")) if today.get("temp") else None
        day_weather = (today.get("weather") or [{}])[0].get("description", "")

        # Interpretive summary
        summary_parts = []
        if max_temp is not None and min_temp is not None:
            if max_temp >= 42:
                summary_parts.append(f"expected to be extremely hot today, with temperatures around {max_temp}°C during the day and about {min_temp}°C at night")
            elif max_temp >= 35:
                summary_parts.append(f"expected to be very warm, with highs near {max_temp}°C and lows around {min_temp}°C")
            else:
                summary_parts.append(f"expected to reach around {max_temp}°C with lows near {min_temp}°C")
        elif temp_now is not None:
            summary_parts.append(f"around {temp_now}°C right now")

        if day_weather:
            summary_parts.append(f"Skies will likely be {day_weather}")

        # rain chance estimate from pop
        pop = today.get("pop")
        if pop is not None:
            if pop >= 0.5:
                summary_parts.append("with a good chance of rain today")
            elif pop >= 0.2:
                summary_parts.append("with some chance of showers")
            else:
                summary_parts.append("with very little chance of rain")

        summary = ", ".join(summary_parts).strip().capitalize() + "."

        # Advice bullets
        advice = []
        if max_temp is not None and max_temp >= 40:
            advice.extend([
                "Avoid direct sun between 12 PM – 4 PM",
                "Stay hydrated",
                "Use light cotton clothes and sunscreen",
                "Limit strenuous outdoor activity",
            ])
        elif max_temp is not None and max_temp >= 30:
            advice.extend([
                "Stay hydrated",
                "Use light clothing and sunscreen",
                "Take breaks if working outside",
            ])
        else:
            advice.extend([
                "Dress for the expected temperature",
                "Carry an umbrella if showers are likely",
            ])

        return {
            "city": name,
            "temp_c": temp_now,
            "feels_like_c": feels,
            "condition": cond,
            "humidity": current.get("humidity"),
            "wind_kph": round(current.get("wind_speed", 0) * 3.6) if current.get("wind_speed") is not None else None,
            "max_temp_c": max_temp,
            "min_temp_c": min_temp,
            "day_condition": day_weather,
            "summary": summary,
            "advice": advice,
        }
    except httpx.HTTPStatusError as e:
        # If API key is invalid (401), fall back to the simpler current weather endpoint.
        resp = getattr(e, "response", None)
        status = getattr(resp, "status_code", None)
        if status == 401:
            # Try current weather endpoint first
            try:
                url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid={WEATHER_API_KEY}&units=metric"
                r = httpx.get(url, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "city": data.get("name", city),
                        "temp_c": round(data.get("main", {}).get("temp")) if data.get("main") else None,
                        "feels_like_c": round(data.get("main", {}).get("feels_like")) if data.get("main") else None,
                        "condition": (data.get("weather") or [{}])[0].get("description", ""),
                        "humidity": data.get("main", {}).get("humidity"),
                        "wind_kph": round(data.get("wind", {}).get("speed", 0) * 3.6) if data.get("wind") else None,
                        "summary": f"{city} weather unavailable from detailed API; current conditions are {((data.get('weather') or [{}])[0].get('description','')).strip()}.",
                        "advice": ["Weather data is limited; check local forecasts if you need precise timing."],
                    }
            except Exception:
                pass

            # Fall back to Open-Meteo (no API key required) using lat/lon
            try:
                om_url = (
                    f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                    f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto"
                )
                om = httpx.get(om_url, timeout=8)
                om.raise_for_status()
                omd = om.json()
                daily = omd.get("daily", {})
                maxs = daily.get("temperature_2m_max", [])
                mins = daily.get("temperature_2m_min", [])
                pops = daily.get("precipitation_probability_max", [])
                max_temp = round(maxs[0]) if maxs else None
                min_temp = round(mins[0]) if mins else None
                pop = pops[0] / 100.0 if pops else None

                summary_parts = []
                if max_temp is not None and min_temp is not None:
                    if max_temp >= 42:
                        summary_parts.append(f"expected to be extremely hot today, with temperatures around {max_temp}°C during the day and about {min_temp}°C at night")
                    else:
                        summary_parts.append(f"expected to reach around {max_temp}°C with lows near {min_temp}°C")

                if pop is not None:
                    if pop >= 0.5:
                        summary_parts.append("with a good chance of rain today")
                    elif pop >= 0.2:
                        summary_parts.append("with some chance of showers")
                    else:
                        summary_parts.append("with very little chance of rain")

                summary = ", ".join(summary_parts).strip().capitalize() + "."
                advice = ["Stay hydrated", "Use light clothing and sunscreen"]
                if max_temp and max_temp >= 40:
                    advice = ["Avoid direct sun between 12 PM – 4 PM", "Stay hydrated", "Use light cotton clothes and sunscreen", "Limit strenuous outdoor activity"]

                return {
                    "city": city,
                    "temp_c": None,
                    "feels_like_c": None,
                    "condition": "",
                    "humidity": None,
                    "wind_kph": None,
                    "max_temp_c": max_temp,
                    "min_temp_c": min_temp,
                    "day_condition": "",
                    "summary": summary,
                    "advice": advice,
                }
            except Exception:
                return {"error": "weather_unavailable"}
        return {"error": "weather_unavailable"}
    except Exception:
        return {"error": "weather_unavailable"}


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
            # Clean up titles that include a trailing ' - SOURCE' to avoid duplicate source display
            suffix = f" - {source}"
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()

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


def _assemble_brief_structured(req, messages) -> tuple[str, list[dict]]:
    # New behavior: produce a top-20 headlines list prioritizing local (city) then country,
    # and include up to 2 articles per user interest inside the top-20 (replace tail items if needed).

    def _parse_rss_items(text, count):
        try:
            root = ET.fromstring(text)
        except Exception:
            return []
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []
        out = []
        for item in items[:count]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "Google News") if source_el is not None else "Google News"
            pub_date = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            out.append({"title": title, "url": link, "source": source, "published": pub_date[:16] if pub_date else ""})
        return out

    def fetch_local_headlines(city, count=20):
        if not city:
            return []
        q = urllib.parse.quote(f"{city} when:1d")
        url = f"https://news.google.com/rss/search?q={q}&hl={GOOGLE_NEWS_HL}&gl={NEWS_COUNTRY}&ceid={GOOGLE_NEWS_CEID}"
        try:
            r = httpx.get(url, timeout=8, follow_redirects=True)
            r.raise_for_status()
            return _parse_rss_items(r.text, count)
        except Exception:
            return []

    def fetch_country_headlines(count=40):
        url = f"https://news.google.com/rss?hl={GOOGLE_NEWS_HL}&gl={NEWS_COUNTRY}&ceid={GOOGLE_NEWS_CEID}"
        try:
            r = httpx.get(url, timeout=8, follow_redirects=True)
            r.raise_for_status()
            return _parse_rss_items(r.text, count)
        except Exception:
            return []

    def fetch_interest_articles(topic, count=2):
        res = search_news(topic, count)
        if res.get("articles"):
            return res.get("articles")
        return []

    city = (req.city or "").strip()
    interests = list(dict.fromkeys([i.strip() for i in (req.interests or []) if i.strip()]))[:5]

    # 1) local headlines
    local = fetch_local_headlines(city, count=20)

    # 2) country headlines (larger pool)
    country = fetch_country_headlines(count=40)

    # dedupe by title/url
    seen = set()
    top = []
    for a in local + country:
        key = (a.get("title"), a.get("url"))
        if key in seen:
            continue
        seen.add(key)
        top.append(a)
        if len(top) >= 20:
            break

    # 3) gather interest articles (2 each)
    interest_articles = []
    for topic in interests:
        arts = fetch_interest_articles(topic, count=2)
        if arts:
            for art in arts:
                key = (art.get("title"), art.get("url"))
                if key not in seen:
                    interest_articles.append(art)
                    seen.add(key)
        else:
            # if no interest articles, we'll let the top headlines absorb an extra country headline
            continue

    # 4) ensure interest articles are in the top-20: replace tail items with interest articles if needed
    final = top[:]
    replace_idx = len(final) - 1
    for art in interest_articles:
        if len(final) < 20:
            final.append(art)
        else:
            if replace_idx < 0:
                replace_idx = len(final) - 1
            final[replace_idx] = art
            replace_idx -= 1

    # If still less than 20 items, try to fill from country pool
    ci = 0
    while len(final) < 20 and ci < len(country):
        a = country[ci]
        key = (a.get("title"), a.get("url"))
        if key not in seen:
            final.append(a)
            seen.add(key)
        ci += 1

    # Greeting using any available weather from messages
    weather = None
    for m in messages:
        if m.get("role") == "tool":
            try:
                content = json.loads(m.get("content") or "{}")
            except Exception:
                continue
            if isinstance(content, dict) and ("temp_c" in content or "condition" in content):
                weather = content
                break

    if weather and weather.get("summary"):
        greeting = f"Good morning — {weather.get('summary')}\n"
    elif weather and weather.get("temp_c") is not None:
        greeting = f"Good morning — {city or weather.get('city','your city')} is {weather['temp_c']}°C and {weather.get('condition','clear')}.\n"
    else:
        greeting = f"Good morning — here's your quick brief for {city or 'your city'}.\n"

    # Build numbered headlines
    lines = [greeting, ""]
    for i, a in enumerate(final[:20], start=1):
        title = a.get("title")
        src = a.get("source", "")
        date = a.get("published", "")
        lines.append(f"{i}. {title} — {src} {date}".strip())

    # If any interests had no updates, we leave the top list as-is (country headlines fill the gaps)

    lines.append("")
    lines.append(f"Thought for the day: Focus on {req.focus_today or 'one clear outcome'} and ship.")

    return "\n".join(lines), final


def _assemble_brief_from_tools(req, messages) -> str:
    """Compatibility wrapper used by tests and older callers: returns only text."""
    text, _items = _assemble_brief_structured(req, messages)
    return text


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
                assembled_text, assembled_items = _assemble_brief_structured(req, messages)
                if assembled_text:
                    final_text = assembled_text
                elif _needs_rewrite(final_text):
                    final_text = _rewrite_brief(req, user_message, final_text, messages)

                if _needs_rewrite(final_text) or not _has_news_content(final_text, req.interests):
                    final_text = _fallback_brief(req)

                final = json.dumps({"type": "brief", "content": final_text})
                yield f"data: {final}\n\n"

                # Emit structured brief (items with title/url/source) if available
                try:
                    struct = json.dumps({"type": "brief_structured", "items": assembled_items})
                    yield f"data: {struct}\n\n"
                except Exception:
                    pass
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
