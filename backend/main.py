import os
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import httpx
import random
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi import Request
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
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")


def build_weather_advice(max_temp=None, pop=None, condition=None, midday_hot=None, hot_hours=None):
    """Return a short list of practical, varied weather advice lines.

    Accepts optional `midday_hot` (bool) and `hot_hours` (list of ints)
    so advice can be time-aware and more specific about when it's hottest.
    """
    templates = []
    # Base heuristics by max temperature
    if max_temp is not None:
        if max_temp >= 45:
            templates = [
                "It's dangerously hot — avoid unnecessary outdoor time around midday.",
                "Sip water frequently; seek air-conditioned or shaded breaks.",
                "Light, breathable cotton or linen and broad-spectrum sunscreen are essential.",
                "Postpone strenuous outdoor tasks until evening if possible.",
            ]
        elif max_temp >= 42:
            templates = [
                "Expect an extremely hot day; avoid direct sun where you can.",
                "Stay hydrated with small, regular sips of water.",
                "Wear breathable cotton/linen and use sunscreen.",
                "Move heavy chores to cooler hours and rest often.",
            ]
        elif max_temp >= 40:
            templates = [
                "Very hot today — avoid the midday sun (12–4 PM).",
                "Keep water nearby and take regular cooling breaks.",
                "Choose lightweight clothes and strong sun protection.",
            ]
        elif max_temp >= 35:
            templates = [
                "Warm to very warm — aim for early-morning or evening activity.",
                "Wear light clothing and use sunscreen when outside.",
                "Stay hydrated and rest in shade when possible.",
            ]
        elif max_temp >= 30:
            templates = [
                "Warm day — keep water handy and take breaks outdoors.",
                "Light clothing and sun protection are a good idea.",
                "Shift heavy work to cooler parts of the day if you can.",
            ]
        elif max_temp >= 25:
            templates = [
                "Mild weather — comfortable for most outdoor plans.",
                "A light layer is probably sufficient; pack sunscreen if sunny.",
            ]
        else:
            templates = [
                "Dress for the expected temperature.",
                "Carry an umbrella if showers are likely.",
            ]

    # Time-aware tweaks
    if midday_hot is True:
        # make sure midday advice appears
        templates.insert(0, "Expect the hottest stretch around midday — avoid 12–4 PM if you can.")
    elif midday_hot is False and hot_hours:
        # If hottest hours are not midday, give a precise heads-up
        try:
            hrs = sorted(set(int(h) for h in hot_hours if isinstance(h, (int, float))))[:3]
            hr_text = ", ".join(f"{h}:00" for h in hrs)
            templates.append(f"Peak heat looks likely around {hr_text}; plan heavy work outside those hours.")
        except Exception:
            pass

    # Rain-based additions
    if pop is not None and pop >= 0.5:
        templates.append("Carry an umbrella or rain jacket — heavy showers possible.")
    elif pop is not None and pop >= 0.2:
        templates.append("A light rain shower is possible; consider a compact umbrella.")

    # Condition-based additions
    if condition:
        c = condition.lower()
        if "haze" in c or "smog" in c or "air quality" in c:
            templates.append("If air quality is poor, limit outdoor exertion and consider a mask.")

    # Choose up to 4 varied items
    # Deduplicate exact strings while preserving order
    seen = set()
    unique = []
    for t in templates:
        if t not in seen:
            unique.append(t)
            seen.add(t)

    # Collapse multiple 'midday/12-4' warnings into a single line
    try:
        midday_indices = [i for i, t in enumerate(unique) if re.search(r"\b(12\s*[–\-–—]?\s*4|12\s*PM|midday|midday sun)\b", t, re.I)]
        if len(midday_indices) > 1:
            # keep the first midday-related template, remove the rest
            for idx in sorted(midday_indices[1:], reverse=True):
                unique.pop(idx)
    except Exception:
        pass

    count = min(4, len(unique))
    try:
        return random.sample(unique, count)
    except Exception:
        return unique[:count]


def _temp_descriptor(max_temp: int | None) -> str:
    """Return a short adjective describing the daytime temperature for summary phrasing."""
    if max_temp is None:
        return "temperatures"
    if max_temp >= 45:
        return "extremely scorching"
    if max_temp >= 42:
        return "extremely hot"
    if max_temp >= 40:
        return "very hot"
    if max_temp >= 35:
        return "very warm"
    if max_temp >= 30:
        return "warm"
    if max_temp >= 25:
        return "mild"
    return "cool"

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
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&hourly=temperature_2m&timezone=auto&current_weather=true"
            )
            om = httpx.get(om_url, timeout=8)
            om.raise_for_status()
            omd = om.json()
            current_weather = omd.get("current_weather", {})
            curr_temp = round(current_weather.get("temperature")) if current_weather.get("temperature") is not None else None
            curr_time = current_weather.get("time")
            daily = omd.get("daily", {})
            maxs = daily.get("temperature_2m_max", [])
            mins = daily.get("temperature_2m_min", [])
            pops = daily.get("precipitation_probability_max", [])
            max_temp = round(maxs[0]) if maxs else None
            min_temp = round(mins[0]) if mins else None
            pop = pops[0] / 100.0 if pops else None

            # Parse hourly temps to detect midday heat and hottest hours
            midday_hot = None
            hot_hours = []
            try:
                hourly = omd.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                hourly_pairs = list(zip(times, temps))
                midday_temps = []
                for tstr, temp in hourly_pairs:
                    try:
                        h = datetime.fromisoformat(tstr).hour
                    except Exception:
                        continue
                    if 12 <= h < 16:
                        midday_temps.append(temp)
                    if temp is not None and temp >= 35:
                        hot_hours.append(h)
                if midday_temps:
                    midday_hot = max(midday_temps) >= 35
            except Exception:
                midday_hot = None
                hot_hours = []

            summary_parts = []
            if max_temp is not None and min_temp is not None:
                desc = _temp_descriptor(max_temp)
                summary_parts.append(f"expected to be {desc} today, with highs around {max_temp}°C and lows near {min_temp}°C")

            if pop is not None:
                if pop >= 0.5:
                    summary_parts.append("with a good chance of rain today")
                elif pop >= 0.2:
                    summary_parts.append("with some chance of showers")
                else:
                    summary_parts.append("with very little chance of rain")

            summary = ", ".join(summary_parts).strip().capitalize() + "."
            advice = build_weather_advice(max_temp=max_temp, pop=pop, condition=None, midday_hot=midday_hot, hot_hours=hot_hours)

            return {
                "city": name,
                "temp_c": curr_temp,
                "feels_like_c": None,
                "condition": "",
                "humidity": None,
                "wind_kph": None,
                "max_temp_c": max_temp,
                "min_temp_c": min_temp,
                "day_condition": "",
                "summary": summary,
                "advice": advice,
                "current_time": curr_time,
                "timezone": omd.get("timezone"),
                "midday_hot": midday_hot,
                "hot_hours": hot_hours,
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

        # 2) onecall for daily forecast (keep hourly for time-aware advice)
        one_url = (
            f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}"
            f"&exclude=minutely,alerts&units=metric&appid={WEATHER_API_KEY}"
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
        # current local time from API (UTC + timezone_offset)
        try:
            tz_off = od.get("timezone_offset", 0) or 0
            curr_dt = current.get("dt")
            if curr_dt is not None:
                current_time = datetime.utcfromtimestamp(curr_dt + tz_off).isoformat()
            else:
                current_time = None
        except Exception:
            current_time = None

        max_temp = round(today.get("temp", {}).get("max")) if today.get("temp") else None
        min_temp = round(today.get("temp", {}).get("min")) if today.get("temp") else None
        # Parse hourly to detect midday heat
        midday_hot = None
        hot_hours = []
        try:
            hourly = od.get("hourly", []) or []
            for hitem in hourly:
                hdt = hitem.get("dt")
                tmp = hitem.get("temp")
                if hdt is None or tmp is None:
                    continue
                local_h = datetime.utcfromtimestamp(hdt + (od.get("timezone_offset", 0) or 0)).hour
                if 12 <= local_h < 16:
                    if midday_hot is None:
                        midday_hot = tmp >= 35
                    else:
                        midday_hot = midday_hot or (tmp >= 35)
                if tmp >= 35:
                    hot_hours.append(local_h)
        except Exception:
            midday_hot = None
            hot_hours = []
        day_weather = (today.get("weather") or [{}])[0].get("description", "")

        # Interpretive summary
        summary_parts = []
        if max_temp is not None and min_temp is not None:
            desc = _temp_descriptor(max_temp)
            summary_parts.append(f"expected to be {desc} today, with highs near {max_temp}°C and lows around {min_temp}°C")
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

        # Advice bullets (time-aware)
        advice = build_weather_advice(max_temp=max_temp, pop=pop, condition=day_weather, midday_hot=midday_hot, hot_hours=hot_hours)

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
            "current_time": current_time,
                "timezone": od.get("timezone"),
                "midday_hot": midday_hot,
                "hot_hours": hot_hours,
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
                    f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&hourly=temperature_2m&timezone=auto&current_weather=true"
                )
                om = httpx.get(om_url, timeout=8)
                om.raise_for_status()
                omd = om.json()
                current_weather = omd.get("current_weather", {})
                curr_temp = round(current_weather.get("temperature")) if current_weather.get("temperature") is not None else None
                curr_time = current_weather.get("time")
                daily = omd.get("daily", {})
                maxs = daily.get("temperature_2m_max", [])
                mins = daily.get("temperature_2m_min", [])
                pops = daily.get("precipitation_probability_max", [])
                max_temp = round(maxs[0]) if maxs else None
                min_temp = round(mins[0]) if mins else None
                pop = pops[0] / 100.0 if pops else None

                # parse hourly for midday-hot detection
                midday_hot = None
                hot_hours = []
                try:
                    hourly = omd.get("hourly", {})
                    times = hourly.get("time", [])
                    temps = hourly.get("temperature_2m", [])
                    for tstr, temp in zip(times, temps):
                        try:
                            h = datetime.fromisoformat(tstr).hour
                        except Exception:
                            continue
                        if 12 <= h < 16 and temp is not None:
                            if midday_hot is None:
                                midday_hot = temp >= 35
                            else:
                                midday_hot = midday_hot or (temp >= 35)
                        if temp is not None and temp >= 35:
                            hot_hours.append(h)
                except Exception:
                    midday_hot = None
                    hot_hours = []

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
                advice = build_weather_advice(max_temp=max_temp, pop=pop, condition=None, midday_hot=midday_hot, hot_hours=hot_hours)

                return {
                    "city": city,
                    "temp_c": curr_temp,
                    "feels_like_c": None,
                    "condition": "",
                    "humidity": None,
                    "wind_kph": None,
                    "max_temp_c": max_temp,
                    "min_temp_c": min_temp,
                    "day_condition": "",
                    "summary": summary,
                    "advice": advice,
                    "current_time": curr_time,
                    "timezone": omd.get("timezone"),
                    "midday_hot": midday_hot,
                    "hot_hours": hot_hours,
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
    hour = datetime.now().hour
    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    return (
        f"{greeting} from {city}.\n\n"
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
            suffix = f" - {source}"
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
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

    # 1) local headlines (prefer a small local slice, but never exceed 10)
    local = fetch_local_headlines(city, count=20)

    # 2) country headlines (India-level pool)
    country = fetch_country_headlines(count=60)

    # 3) interest articles: fetch globally (not constrained to local) up to 3 each
    def fetch_interest_articles_global(topic, count=3):
        try:
            q = urllib.parse.quote(topic)
            url = f"https://news.google.com/rss/search?q={q}%20when%3A1d&hl=en&ceid=US:en"
            r = httpx.get(url, timeout=8, follow_redirects=True)
            r.raise_for_status()
            return _parse_rss_items(r.text, count)
        except Exception:
            return []

    # target distribution: prefer 6 local, then interest articles (3 per interest), fill remaining with India headlines
    preferred_local = 6
    local_limit = min(10, 20)
    local_selected = []
    seen = set()

    # pick up to preferred_local (but not exceeding local_limit)
    for a in local[:min(preferred_local, local_limit)]:
        key = (a.get("title"), a.get("url"))
        if key in seen:
            continue
        seen.add(key)
        local_selected.append(a)

    # gather interest articles (3 each) globally
    interest_articles = []
    for topic in interests:
        arts = fetch_interest_articles_global(topic, count=3)
        for art in arts:
            key = (art.get("title"), art.get("url"))
            if key not in seen:
                interest_articles.append(art)
                seen.add(key)

    # build final list: start with local_selected, then interest_articles, then fill with country headlines
    final = []
    final.extend(local_selected)
    final.extend(interest_articles)

    for a in country:
        if len(final) >= 20:
            break
        key = (a.get("title"), a.get("url"))
        if key in seen:
            continue
        seen.add(key)
        final.append(a)

    # ensure exactly 20 items max
    final = final[:20]

    # Greeting using any available weather from messages (time-aware)
    weather = None
    for m in messages:
        if m.get("role") == "tool":
            try:
                content = json.loads(m.get("content") or "{}")
            except Exception:
                continue
            if isinstance(content, dict) and ("temp_c" in content or "condition" in content or "current_time" in content):
                weather = content
                break

    # Determine local time (prefer weather current_time or timezone if available)
    local_dt = None
    # If weather doesn't provide timezone, try geocoding city to find timezone
    if (not weather or not weather.get("timezone")) and city:
        try:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en"
            gg = httpx.get(geo_url, timeout=6)
            gg.raise_for_status()
            gj = gg.json() or {}
            res = gj.get("results") or []
            if res and not weather:
                # if we have no weather object yet, populate minimal timezone
                weather = {"timezone": res[0].get("timezone")}
            elif res and weather and not weather.get("timezone"):
                weather["timezone"] = res[0].get("timezone")
        except Exception:
            pass
    if weather and weather.get("current_time"):
        try:
            # parse ISO time from weather; may be naive (local) or include offset
            local_dt = datetime.fromisoformat(weather.get("current_time"))
            # attach timezone info if provided
            if weather.get("timezone") and ZoneInfo is not None:
                try:
                    local_dt = local_dt.replace(tzinfo=ZoneInfo(weather.get("timezone")))
                except Exception:
                    pass
        except Exception:
            local_dt = None
    if local_dt is None and weather and weather.get("timezone") and ZoneInfo is not None:
        try:
            local_dt = datetime.now(ZoneInfo(weather.get("timezone")))
        except Exception:
            local_dt = None
    if local_dt is None:
        local_dt = datetime.now()

    hour = local_dt.hour
    if 5 <= hour < 12:
        greeting_word = "Good morning"
    elif 12 <= hour < 17:
        greeting_word = "Good afternoon"
    else:
        # Late night / early morning
        greeting_word = "Good evening"

    # Compose greeting with current temp if available
    if weather and weather.get("temp_c") is not None:
        greeting = f"{greeting_word} — {city or weather.get('city','your city')} is {weather['temp_c']}°C and {weather.get('condition','clear')}.\n"
    elif weather and weather.get("summary"):
        greeting = f"{greeting_word} — {weather.get('summary')}\n"
    else:
        greeting = f"{greeting_word} — here's your quick brief for {city or 'your city'}.\n"

    # Add generated timestamp (local)
    gen_time = local_dt.strftime("%I:%M %p").lstrip("0")
    greeting += f"Generated at {gen_time}\n"

    # Adjust summary wording for night readers: mention tonight/tomorrow when appropriate
    if weather:
        max_t = weather.get("max_temp_c")
        min_t = weather.get("min_temp_c")
        # If reading at night, prefer 'Tonight'/'Tomorrow' phrasing
        if hour < 6 or hour >= 20:
            if min_t is not None and max_t is not None:
                night_summary = f"Tonight: lows around {min_t}°C. Tomorrow expect highs near {max_t}°C."
                # prepend to greeting summary area
                greeting = f"{greeting}\n{night_summary}\n"
        else:
            # keep existing weather summary as-is (if provided)
            if weather.get("summary"):
                # ensure summary ends with a period
                s = weather.get("summary").strip()
                if not s.endswith("."):
                    s = s + "."
                greeting = f"{greeting}\n{s}\n"

        # Append a few concise weather advice lines when available
        if weather.get("advice"):
            # ensure a separating newline
            if not greeting.endswith("\n"):
                greeting += "\n"
            for adv in weather.get("advice")[:4]:
                greeting += f"{adv}\n"

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


async def _supabase_get_user(access_token: str) -> dict | None:
    """Return the Supabase auth user object for a bearer token, or None."""
    if not SUPABASE_URL or not access_token:
        return None
    try:
        url = SUPABASE_URL.rstrip("/") + "/auth/v1/user"
        r = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=6)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _supabase_get_profile_city(user_id: str) -> str | None:
    """Fetch the `city` for a given user_id from the Supabase `profiles` table using service key."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not user_id:
        return None
    try:
        url = SUPABASE_URL.rstrip("/") + f"/rest/v1/profiles?select=city&user_id=eq.{user_id}"
        headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        }
        r = httpx.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            data = r.json() or []
            if data:
                return data[0].get("city")
    except Exception:
        pass
    return None


def _supabase_upsert_profile(user_id: str, email: str | None, city: str) -> bool:
    """Upsert a profile row (user_id, email, city) using the service role key."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not user_id:
        return False
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/profiles"
        headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        payload = {"user_id": user_id, "email": email, "city": city}
        r = httpx.post(url, headers=headers, json=payload, timeout=6)
        return r.status_code in (200, 201)
    except Exception:
        return False


# ── Agentic streaming endpoint ────────────────────────────────────────────────

@app.post("/brief")
async def generate_brief(req: BriefRequest, request: Request):
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

    # If Authorization header present and city not provided, attempt to fill from Supabase profile
    try:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer") and (not req.city or not req.city.strip()):
            token = auth.split(None, 1)[1].strip()
            user = await _supabase_get_user(token)
            if user and isinstance(user, dict):
                uid = user.get("id") or user.get("sub")
                if uid:
                    city = _supabase_get_profile_city(uid)
                    if city:
                        req.city = city
    except Exception:
        pass

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


class ProfilePayload(BaseModel):
    city: str


@app.post("/profile")
async def upsert_profile(payload: ProfilePayload, request: Request):
    """Upsert the authenticated user's profile (city). Requires Authorization: Bearer <access_token>."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer"):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth.split(None, 1)[1].strip()
    user = await _supabase_get_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    uid = user.get("id") or user.get("sub")
    email = user.get("email")
    ok = _supabase_upsert_profile(uid, email, payload.city)
    if not ok:
        raise HTTPException(status_code=500, detail="Could not upsert profile")
    return {"status": "ok", "city": payload.city}


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
