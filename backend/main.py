import os
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import httpx
import random
import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from groq import Groq
import pytz

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, save_user_tokens, update_user_settings, get_user, get_all_users

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

# Google OAuth Credentials
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")

SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]

client_config = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [GOOGLE_REDIRECT_URI]
    }
}

# ── Weather helpers ────────────────────────────────────────────────────────────

def _temp_descriptor(temp: float) -> str:
    if temp >= 40:
        return "extremely hot"
    if temp >= 35:
        return "very hot"
    if temp >= 30:
        return "hot"
    if temp >= 25:
        return "warm"
    if temp >= 20:
        return "mild"
    if temp >= 15:
        return "cool"
    return "cold"

def build_weather_advice(max_temp=None, pop=None, condition=None, midday_hot=None, hot_hours=None):
    templates = []
    if max_temp is not None:
        if max_temp >= 45:
            templates = [
                "It's dangerously hot — avoid unnecessary outdoor time around midday.",
                "Sip water frequently; seek air-conditioned or shaded breaks.",
                "Light, breathable cotton or linen and broad-spectrum sunscreen are essential.",
            ]
        elif max_temp >= 40:
            templates = [
                "Very hot today — avoid direct sun in the afternoon.",
                "Keep water nearby and take regular cooling breaks.",
                "Choose lightweight clothes and strong sun protection.",
            ]
        elif max_temp >= 30:
            templates = [
                "Warm day — keep water handy.",
                "Light clothing is a good idea.",
            ]
        elif max_temp >= 20:
            templates = [
                "Mild weather — comfortable for outdoor plans.",
                "A light layer is probably sufficient.",
            ]
        else:
            templates = [
                "Dress for the cold temperature.",
            ]

    if midday_hot is True:
        templates.insert(0, "Expect the hottest stretch around midday — avoid 12–4 PM if you can.")
    elif midday_hot is False and hot_hours:
        try:
            hrs = sorted(set(int(h) for h in hot_hours))[:3]
            hr_text = ", ".join(f"{h}:00" for h in hrs)
            templates.append(f"Peak heat looks likely around {hr_text}; plan heavy work outside those hours.")
        except Exception:
            pass

    if pop is not None and pop >= 0.4:
        templates.append("High probability of precipitation today. Carry an umbrella!")

    return templates

def get_weather(city: str) -> dict:
    try:
        if USE_OPEN_METEO:
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
            pop = (pops[0] / 100.0) if pops else None

            midday_hot = None
            hot_hours = []
            try:
                hourly = omd.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                for tstr, temp in zip(times, temps):
                    try:
                        h = datetime.datetime.fromisoformat(tstr).hour
                    except Exception:
                        continue
                    if 12 <= h < 16:
                        if midday_hot is None:
                            midday_hot = temp >= 35
                        else:
                            midday_hot = midday_hot or (temp >= 35)
                    if temp is not None and temp >= 35:
                        hot_hours.append(h)
            except Exception:
                pass

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
                "max_temp_c": max_temp,
                "min_temp_c": min_temp,
                "summary": summary,
                "advice": advice,
                "current_time": curr_time,
                "timezone": omd.get("timezone"),
            }

        if not WEATHER_API_KEY:
            return {"error": "OPENWEATHER_API_KEY not set"}

        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={urllib.parse.quote(city)}&limit=1&appid={WEATHER_API_KEY}"
        g = httpx.get(geo_url, timeout=8)
        g.raise_for_status()
        geo = g.json() or []
        if not geo:
            return {"error": f"Could not geocode {city}"}
        lat = geo[0]["lat"]
        lon = geo[0]["lon"]
        name = geo[0].get("name", city)

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
        day_weather = (today.get("weather") or [{}])[0].get("description", "")
        max_temp = round(today.get("temp", {}).get("max")) if today.get("temp") else None
        min_temp = round(today.get("temp", {}).get("min")) if today.get("temp") else None
        pop = today.get("pop")

        summary_parts = []
        if max_temp is not None and min_temp is not None:
            desc = _temp_descriptor(max_temp)
            summary_parts.append(f"expected to be {desc} today, with highs near {max_temp}°C and lows around {min_temp}°C")

        if pop is not None:
            if pop >= 0.5:
                summary_parts.append("with a good chance of rain today")
            elif pop >= 0.2:
                summary_parts.append("with some chance of showers")
            else:
                summary_parts.append("with very little chance of rain")

        summary = ", ".join(summary_parts).strip().capitalize() + "."
        advice = build_weather_advice(max_temp=max_temp, pop=pop, condition=day_weather)

        return {
            "city": name,
            "temp_c": temp_now,
            "max_temp_c": max_temp,
            "min_temp_c": min_temp,
            "summary": summary,
            "advice": advice,
            "current_time": datetime.datetime.now().isoformat(),
            "timezone": od.get("timezone"),
        }
    except Exception as e:
        print(f"Weather error: {e}")
        return {"error": "weather_unavailable"}

# ── News helpers ──────────────────────────────────────────────────────────────

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
            suffix = f" - {source}"
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()

            articles.append({
                "title": title,
                "source": source,
                "url": link,
                "published": pub_date[:16] if pub_date else "",
            })

        return {"topic": topic, "articles": articles}
    except Exception as e:
        return {"error": str(e)}

# ── Google API helpers ─────────────────────────────────────────────────────────

def get_credentials_for_user(email: str):
    user_data = get_user(email)
    if not user_data:
        return None
    
    creds = Credentials(
        token=user_data.get("access_token"),
        refresh_token=user_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES
    )
    
    if creds.expired or not creds.valid:
        try:
            creds.refresh(Request())
            save_user_tokens(email, creds.refresh_token, creds.token)
        except Exception as e:
            print(f"Failed to refresh Google token for {email}: {e}")
            return None
            
    return creds

def get_calendar_events_for_day(creds, timezone_name="Asia/Kolkata"):
    try:
        service = build("calendar", "v3", credentials=creds)
        tz = pytz.timezone(timezone_name)
        now = datetime.datetime.now(tz)
        
        start_of_today = datetime.datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=now.tzinfo)
        end_of_today = datetime.datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=now.tzinfo)
        
        time_min = start_of_today.isoformat()
        time_max = end_of_today.isoformat()
        
        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        events = events_result.get("items", [])
        
        formatted_events = []
        for event in events:
            start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
            summary = event.get("summary", "No Title")
            location = event.get("location", "")
            
            time_str = "All Day"
            if "dateTime" in event.get("start", {}):
                # Parsing string like 2026-07-05T14:30:00+05:30
                try:
                    dt = datetime.datetime.fromisoformat(start)
                    time_str = dt.strftime("%I:%M %p")
                except Exception:
                    time_str = "Scheduled"
                
            formatted_events.append({
                "title": summary,
                "time": time_str,
                "location": location
            })
            
        return formatted_events
    except Exception as e:
        print(f"Calendar fetch error: {e}")
        return []

def get_recent_emails(creds):
    try:
        service = build("gmail", "v3", credentials=creds)
        results = service.users().messages().list(
            userId="me",
            labelIds=["INBOX"],
            maxResults=10,
            q="category:primary"
        ).execute()
        
        messages = results.get("messages", [])
        emails = []
        
        for msg in messages:
            msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
            headers = msg_data.get("payload", {}).get("headers", [])
            
            subject = "No Subject"
            sender = "Unknown Sender"
            for h in headers:
                if h["name"].lower() == "subject":
                    subject = h["value"]
                elif h["name"].lower() == "from":
                    sender = h["value"]
                    
            snippet = msg_data.get("snippet", "")
            
            emails.append({
                "from": sender,
                "subject": subject,
                "snippet": snippet
            })
            
        return emails
    except Exception as e:
        print(f"Gmail fetch error: {e}")
        return []

# ── Groq digest generator ──────────────────────────────────────────────────────

def generate_groq_digest(city, weather, calendar, gmail, news, focus):
    system_prompt = (
        "You are the master editor of 'The Daily AI Chronicle', a premium, highly personalized morning newspaper.\n"
        "Your task is to take raw inputs (weather details, calendar meetings, recent email snippets, news articles, and user focus) "
        "and draft a high-quality newspaper edition in JSON format.\n\n"
        "Guidelines:\n"
        "- Assess the weather details. If precipitation, rain, or adverse conditions are forecast, write a friendly warning advisory (e.g. 'Heavy rain expected in evening. Carry an umbrella!', 'Carry an umbrella!').\n"
        "- Summarize the calendar events into a short editorial highlight column ('calendar_editorial') and return the formatted event items.\n"
        "- Analyze the email snippets for key threads, flight tickets, urgent reminders. Summarize into a correspondence highlight column ('inbox_editorial') and list key email items.\n"
        "- Summarize the news articles by topic in a brief journalistic style.\n"
        "- Ensure the tone is elegant, slightly vintage/witty, and professional.\n"
        "- The output must be valid JSON matching the schema.\n\n"
        "Required JSON schema:\n"
        "{\n"
        "  \"greeting\": \"A short editor greeting (e.g. Good morning Ahmedabad. A warm day is ahead...)\",\n"
        "  \"advisory\": \"Weather warning/advice, or empty if none\",\n"
        "  \"calendar_editorial\": \"Short editorial text highlighting the day's schedule\",\n"
        "  \"calendar_items\": [{\"time\": \"time\", \"title\": \"event title\", \"location\": \"location or empty\"}],\n"
        "  \"inbox_editorial\": \"Short editorial text summarizing email activity\",\n"
        "  \"inbox_items\": [{\"from\": \"sender name\", \"subject\": \"email subject\", \"summary\": \"1-sentence summary of content\"}],\n"
        "  \"news_columns\": [{\"topic\": \"topic\", \"articles\": [{\"title\": \"title\", \"source\": \"source\", \"summary\": \"1-sentence summary of news\"}]}],\n"
        "  \"thought_of_the_day\": \"An inspiring or witty closing quote/thought\"\n"
        "}"
    )
    
    user_content = json.dumps({
        "city": city,
        "weather": weather,
        "calendar": calendar,
        "gmail": gmail,
        "news": news,
        "focus_today": focus
    })
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
            max_tokens=2000
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error calling Groq client: {e}")
        return {
            "greeting": f"Good morning. Welcome to your daily brief.",
            "advisory": "",
            "calendar_editorial": "No schedule details available.",
            "calendar_items": [],
            "inbox_editorial": "No email summaries available.",
            "inbox_items": [],
            "news_columns": [],
            "thought_of_the_day": "Carpe Diem."
        }

# ── Email Delivery helpers ─────────────────────────────────────────────────────

def render_newspaper_html(digest, city):
    date_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
    time_str = datetime.datetime.now().strftime("%I:%M %p")
    
    advisory_html = ""
    if digest.get("advisory"):
        advisory_html = f'<div class="advisory-box">ADVISORY: {digest["advisory"]}</div>'
        
    calendar_events_html = ""
    if digest.get("calendar_items"):
        for item in digest["calendar_items"]:
            loc_str = f" ({item['location']})" if item.get('location') else ""
            calendar_events_html += f'<div class="event-row"><span class="event-time">{item["time"]}</span> {item["title"]}{loc_str}</div>'
    else:
        calendar_events_html = '<div class="event-row" style="color: #666;">No scheduled events for today.</div>'
        
    inbox_emails_html = ""
    if digest.get("inbox_items"):
        for item in digest["inbox_items"]:
            inbox_emails_html += f'<div class="event-row"><strong style="color: #C2410C;">From: {item["from"]}</strong> - {item["subject"]} <br><span style="font-size: 11px; color: #555; font-style: italic;">{item["summary"]}</span></div>'
    else:
        inbox_emails_html = '<div class="event-row" style="color: #666;">No recent unread messages.</div>'
        
    news_html = ""
    if digest.get("news_columns"):
        for col in digest["news_columns"]:
            news_html += f'<h3 style="font-size: 15px; border-bottom: 1px dotted #1A1A1A; margin-top: 15px; padding-bottom: 2px; text-transform: uppercase;">{col["topic"]}</h3>'
            for art in col.get("articles", []):
                news_html += f'<div class="article"><div class="article-title">{art["title"]}</div><div class="article-meta">Source: {art.get("source", "News")}</div><div class="article-body">{art.get("summary", "")}</div></div>'
                
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            background-color: #F6F3EB;
            color: #1A1A1A;
            font-family: 'Times New Roman', Georgia, serif;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 650px;
            margin: 0 auto;
            border: 3px double #1A1A1A;
            padding: 20px;
            background-color: #FAF7F0;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #1A1A1A;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }}
        .header h1 {{
            font-size: 34px;
            margin: 0 0 5px 0;
            font-weight: normal;
            letter-spacing: 2px;
            text-transform: uppercase;
        }}
        .header .meta {{
            font-size: 13px;
            font-style: italic;
            border-top: 1px solid #1A1A1A;
            border-bottom: 1px solid #1A1A1A;
            padding: 4px 0;
            margin-top: 5px;
            display: flex;
            justify-content: space-between;
        }}
        .advisory-box {{
            background-color: #FFF0EB;
            border: 1px solid #C2410C;
            padding: 10px;
            margin-bottom: 20px;
            font-size: 13px;
            color: #C2410C;
            font-weight: bold;
            text-align: center;
        }}
        .section-title {{
            font-size: 18px;
            text-transform: uppercase;
            border-bottom: 1px solid #1A1A1A;
            padding-bottom: 2px;
            margin-top: 25px;
            margin-bottom: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        }}
        .article {{
            margin-bottom: 15px;
            line-height: 1.5;
        }}
        .article-title {{
            font-size: 15px;
            font-weight: bold;
            margin-bottom: 2px;
        }}
        .article-meta {{
            font-size: 11px;
            color: #666;
            margin-bottom: 4px;
        }}
        .article-body {{
            font-size: 13px;
            text-align: justify;
        }}
        .event-row {{
            font-size: 13px;
            margin-bottom: 8px;
            border-bottom: 1px dashed #DDD;
            padding-bottom: 4px;
            line-height: 1.4;
        }}
        .event-time {{
            font-weight: bold;
            color: #C2410C;
            display: inline-block;
            width: 80px;
        }}
        .footer {{
            text-align: center;
            border-top: 1px solid #1A1A1A;
            margin-top: 30px;
            padding-top: 15px;
            font-size: 14px;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>The Daily AI Chronicle</h1>
            <div class="meta">
                <span>Vol. II · No. 24</span>
                <span>{date_str}</span>
                <span>{city} Edition</span>
            </div>
        </div>
        
        {advisory_html}
        
        <div class="article">
            <p style="font-size: 14px; font-style: italic; line-height: 1.5; margin: 0 0 15px 0;">{digest.get("greeting")}</p>
        </div>
        
        <div class="section-title">The Daily Docket (Calendar)</div>
        <div class="article">
            <p class="article-body" style="margin-bottom: 10px;">{digest.get("calendar_editorial")}</p>
            {calendar_events_html}
        </div>
        
        <div class="section-title">The Correspondence Desk (Inbox)</div>
        <div class="article">
            <p class="article-body" style="margin-bottom: 10px;">{digest.get("inbox_editorial")}</p>
            {inbox_emails_html}
        </div>
        
        <div class="section-title">Chronicles & Headlines</div>
        {news_html}
        
        <div class="footer">
            <p>"{digest.get("thought_of_the_day")}"</p>
            <small style="color: #888; font-size: 10px;">Delivered at {time_str}. Generated by Varta AI.</small>
        </div>
    </div>
</body>
</html>
"""

def send_digest_email(creds, email_address, subject, html_content):
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    
    try:
        service = build("gmail", "v3", credentials=creds)
        
        message = MIMEMultipart("alternative")
        message["to"] = email_address
        message["from"] = "me"
        message["subject"] = subject
        
        part = MIMEText(html_content, "html")
        message.attach(part)
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        service.users().messages().send(
            userId="me",
            body={"raw": raw_message}
        ).execute()
        return True
    except Exception as e:
        print(f"Gmail send API error: {e}")
        return False

def generate_and_send_digest_email_sync(email: str):
    creds = get_credentials_for_user(email)
    if not creds:
        print(f"[Sync] Credentials missing for {email}")
        return
        
    user_settings = get_user(email)
    city = user_settings.get("city") or "Ahmedabad"
    interests_str = user_settings.get("interests") or "Technology"
    interests = [i.strip() for i in interests_str.split(",") if i.strip()]
    timezone_name = user_settings.get("timezone") or "Asia/Kolkata"
    
    weather_info = get_weather(city)
    calendar_events = get_calendar_events_for_day(creds, timezone_name)
    gmail_emails = get_recent_emails(creds)
    
    news_articles = []
    for interest in interests[:3]:
        articles = search_news(interest)
        if articles and "articles" in articles:
            news_articles.append({
                "topic": interest,
                "articles": articles["articles"][:3]
            })
            
    digest = generate_groq_digest(city, weather_info, calendar_events, gmail_emails, news_articles, "")
    html_content = render_newspaper_html(digest, city)
    
    date_str = datetime.datetime.now().strftime("%B %d, %Y")
    subject = f"The Morning Chronicle — {date_str}"
    
    send_digest_email(creds, email, subject, html_content)

# ── API Routes ─────────────────────────────────────────────────────────────────

@app.get("/auth/login")
def auth_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google client credentials are not configured in environment.")
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true"
    )
    
    return {"url": authorization_url}

@app.get("/auth/callback")
async def auth_callback(code: str, state: str = None):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google credentials not configured")
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    # Get user email
    async with httpx.AsyncClient() as http_client:
        res = await http_client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"}
        )
        if res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info from Google")
        user_info = res.json()
        email = user_info.get("email")
        
    if not email:
        raise HTTPException(status_code=400, detail="Google response did not return an email address")
    
    # Save tokens to database
    save_user_tokens(email, creds.refresh_token, creds.token)
    
    frontend_url = os.environ.get("VITE_FRONTEND_URL", "http://localhost:5173")
    redirect_target = f"{frontend_url}/?email={urllib.parse.quote(email)}"
    
    return RedirectResponse(redirect_target)

class SettingsRequest(BaseModel):
    email: str
    city: str
    interests: list[str] = Field(default_factory=list)
    delivery_time: str
    timezone: str
    enabled: bool

@app.post("/settings")
def save_settings(req: SettingsRequest):
    interests_str = ", ".join([i.strip() for i in req.interests if i.strip()])
    update_user_settings(
        req.email,
        req.city,
        interests_str,
        req.delivery_time,
        req.timezone,
        req.enabled
    )
    return {"status": "ok"}

@app.get("/settings")
def get_settings(email: str):
    user_settings = get_user(email)
    if not user_settings:
        raise HTTPException(status_code=404, detail="User not found")
    
    interests_list = [i.strip() for i in user_settings.get("interests", "").split(",") if i.strip()]
    
    return {
        "email": user_settings.get("email"),
        "city": user_settings.get("city") or "",
        "interests": interests_list,
        "delivery_time": user_settings.get("delivery_time") or "07:00",
        "timezone": user_settings.get("timezone") or "Asia/Kolkata",
        "enabled": bool(user_settings.get("enabled", 1))
    }

class BriefRequest(BaseModel):
    email: str
    city_override: str = ""
    interests_override: list[str] = Field(default_factory=list)
    focus_today: str = ""

@app.post("/brief")
async def generate_brief(req: BriefRequest):
    email = req.email
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
        
    creds = get_credentials_for_user(email)
    if not creds:
        raise HTTPException(status_code=401, detail="Google authentication required")
        
    user_settings = get_user(email)
    if not user_settings:
        # Save a placeholder user entry since they already authorized Google
        save_user_tokens(email, None, creds.token)
        user_settings = get_user(email)
        
    city = req.city_override or user_settings.get("city") or "Ahmedabad"
    interests_list = req.interests_override or [i.strip() for i in (user_settings.get("interests") or "Technology").split(",") if i.strip()]
    timezone_name = user_settings.get("timezone") or "Asia/Kolkata"
    
    # 1. Fetch weather
    weather_info = get_weather(city)
    
    # 2. Fetch Google Calendar
    calendar_events = get_calendar_events_for_day(creds, timezone_name)
    
    # 3. Fetch Gmail
    gmail_emails = get_recent_emails(creds)
    
    # 4. Fetch News
    news_articles = []
    for interest in interests_list[:3]:
        articles = search_news(interest)
        if articles and "articles" in articles:
            news_articles.append({
                "topic": interest,
                "articles": articles["articles"][:3]
            })
            
    # 5. Call Groq
    digest = generate_groq_digest(city, weather_info, calendar_events, gmail_emails, news_articles, req.focus_today)
    
    return digest

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.datetime.now().isoformat()}

# ── Scheduler ──────────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()

def check_and_send_daily_digests():
    users = get_all_users()
    for user in users:
        if not user.get("enabled"):
            continue
            
        email = user.get("email")
        delivery_time_str = user.get("delivery_time", "07:00")
        timezone_str = user.get("timezone", "Asia/Kolkata")
        
        try:
            tz = pytz.timezone(timezone_str)
            now = datetime.datetime.now(tz)
        except Exception:
            now = datetime.datetime.now()
            
        current_time_str = now.strftime("%H:%M")
        
        if current_time_str == delivery_time_str:
            print(f"[Scheduler] Triggering morning newspaper email for {email} at local time {current_time_str}")
            try:
                generate_and_send_digest_email_sync(email)
            except Exception as e:
                print(f"[Scheduler] Error sending daily digest to {email}: {e}")

@app.on_event("startup")
def startup_event():
    init_db()
    # Check every minute on the 0th second
    scheduler.add_job(check_and_send_daily_digests, "cron", second="0")
    scheduler.start()
    print("Background scheduler started successfully.")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
