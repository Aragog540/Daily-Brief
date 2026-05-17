# ◈ DailyBrief

**Your agentic morning intelligence — powered by Groq + LLaMA 3.1**

DailyBrief is an agentic AI web app that generates a personalized morning briefing in seconds. You tell it your city, your interests, and what you're focused on today. An LLM agent autonomously calls weather, news, and date tools — then synthesizes everything into one clean, human-sounding brief.

Built for portfolios. Deployable in 30 minutes. Free to run.

---

## What makes it "agentic"

Most AI apps are wrappers — you send a prompt, get a response. DailyBrief is different. The LLM **decides** which tools to call, in what order, and how to combine their results:

```
User input
    ↓
Agent decides: call get_day_context()   → today is Tuesday, May 2025
Agent decides: call get_weather("Ahmedabad")  → 38°C, hazy sunshine
Agent decides: call search_news("AI & ML")    → 3 relevant articles
Agent decides: call search_news("Cricket")    → 3 more articles
    ↓
Agent synthesizes everything into a personalized brief
    ↓
Live trace shown to user as it happens
```

The **agent trace panel** in the UI makes this visible — users watch the agent work in real time, which is the whole portfolio story.

---

## Tech stack

| Layer | Technology |
|---|---|
| LLM | Groq API — `llama-3.1-8b-instant` |
| Backend | FastAPI (Python) |
| Frontend | React + Vite |
| Weather | OpenWeatherMap API (free tier) |
| News | NewsAPI (free tier) |
| Deploy | Render Web Service (free tier) |

**Why Groq?** Speed. `llama-3.1-8b-instant` runs 5–10× faster than comparable models on other providers. For a morning brief with multiple tool calls, this means a ~5 second total experience vs 30+ seconds elsewhere — critical for UX.

**Why 8B not 70B?** The Groq free tier is generous but has token-per-minute limits. The 8B model handles tool calling + synthesis perfectly and uses ~4× fewer tokens, keeping you well within free tier limits.

---

## Project structure

```
dailybrief/
├── backend/
│   ├── main.py              # FastAPI app + agentic loop
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Root component, SSE streaming logic
│   │   ├── index.css        # Full design system
│   │   └── components/
│   │       ├── BriefForm.jsx    # City, interests, focus input
│   │       ├── AgentTrace.jsx   # Live tool-call trace panel
│   │       └── BriefOutput.jsx  # Rendered final brief
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── render.yaml              # Optional Render service config
├── .gitignore
└── README.md
```

---

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Accounts (all free): [Groq](https://console.groq.com), [OpenWeatherMap](https://openweathermap.org/api), [NewsAPI](https://newsapi.org)

### 1. Clone and set up backend

```bash
git clone https://github.com/your-username/dailybrief.git
cd dailybrief/backend

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your three API keys
```

### 2. Run the backend

```bash
uvicorn main:app --reload --port 8000
```

Test it: open [http://localhost:8000/health](http://localhost:8000/health)

### 3. Set up and run the frontend

```bash
cd ../frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

> The frontend uses relative API paths by default, so local Vite proxying and same-origin production both work.

---

## Getting your API keys

### Groq (LLM)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up → API Keys → Create API Key
3. Free tier: generous limits, no credit card needed

### OpenWeatherMap (weather)
1. Go to [openweathermap.org](https://openweathermap.org/api)
2. Sign up → My API Keys → copy the default key
3. Free tier: 60 calls/minute — more than enough
4. Note: new keys take ~10 minutes to activate

### NewsAPI (news)
1. Go to [newsapi.org](https://newsapi.org)
2. Get API Key → copy it
3. Free tier: 100 requests/day, developer use only
4. Note: free tier doesn't allow production use for commercial apps — fine for portfolios

---

## Deploy to Render

### Manual Web Service setup

1. Push your code to GitHub.
2. Go to [render.com](https://render.com) → New → Web Service.
3. Connect this repository.
4. Set the root directory to the repository root, not `backend` or `frontend`.
5. Use these commands:
    - Build: `pip install --upgrade pip setuptools wheel && pip install -r requirements.txt && cd frontend && npm ci && npm run build`
    - Start: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Make sure Render uses Python 3.12 for this service. The repo includes a root `runtime.txt` for that.
7. Add these environment variables in Render:
    - `GROQ_API_KEY`
    - `OPENWEATHER_API_KEY`
    - `NEWS_API_KEY`
8. Deploy.
9. Open the service URL when the deploy finishes. The FastAPI app serves both the API and the built React frontend.

### Render notes

- You do not need a separate static site.
- You do not need `VITE_API_URL` for this deployment, because the frontend calls the API on the same origin.
- If you later split the frontend into a separate deployment, set `VITE_API_URL` to the backend URL.
- Free web services spin down after 15 minutes of inactivity. The first request after sleep may take around 30 seconds.

---

## How the agentic loop works (for interviews)

The core of the project is in `backend/main.py`. Here's the loop:

```python
for _ in range(8):                          # max iterations
    response = groq.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,                  # full conversation history
        tools=TOOLS,                        # tool definitions (JSON schema)
        tool_choice="auto",                 # LLM decides when to call tools
    )

    if response has tool_calls:
        for each tool_call:
            stream trace event to frontend  # SSE
            execute the actual function
            stream result to frontend       # SSE
            append to messages             # agent remembers results

    if finish_reason == "stop":
        stream final brief to frontend
        return
```

The agent pattern: give the LLM tools + history, let it call tools, feed results back, repeat until it decides it has enough to answer. This is **ReAct** (Reason + Act) — the most common agentic pattern.

---

## Extending the project

Some ideas if you want to go further:

- **Memory:** Store user preferences in localStorage so they don't re-enter city/interests each time
- **Scheduling:** Add a "remind me at 7am" feature using a cron job on Render
- **More tools:** Add `get_calendar_events()` (Google Calendar API), `get_top_of_hacker_news()`, or `get_currency_rate()`
- **Streaming text:** Stream the final brief word-by-word instead of all at once (Groq supports streaming)
- **History:** Save past briefs to a simple SQLite database and show a "past briefs" page

---

## License

MIT — use it, fork it, put it in your portfolio.

---

*Built with Groq · LLaMA 3.1 · FastAPI · React*
