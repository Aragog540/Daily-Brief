# ◈ Varta AI

**Your agentic morning briefing app.**

Varta AI asks for your city, interests, and what you're focused on, then uses Groq, weather, and news tools to generate a short morning brief with a live agent trace.

## Stack

- Backend: FastAPI
- Frontend: React + Vite
- LLM: Groq `llama-3.1-8b-instant`
- APIs: OpenWeatherMap, Google News RSS
- Deploy: Render Web Service

## Local Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Deploy to Render

1. Create a new Web Service and connect this repo.
2. Set the root directory to the repo root.
3. Use this build command: `pip install --upgrade pip setuptools wheel && pip install -r requirements.txt && cd frontend && npm ci && npm run build`
4. Use this start command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add `GROQ_API_KEY` and `OPENWEATHER_API_KEY`.
6. Deploy.

## Notes

- The app serves both the API and the frontend from the FastAPI backend.
- News comes from Google News RSS and is scoped to India.
- The repo pins Python 3.14 in `runtime.txt`.
- You do not need `VITE_API_URL` for the single-service setup.

## Setup Environment Variables

### Backend (`backend/.env`):
```env
OPENWEATHER_API_KEY=your_openweather_key_here
GROQ_API_KEY=your_groq_key_here
USE_OPEN_METEO=false
```

### Frontend (`frontend/.env`):
```env
VITE_API_URL=http://localhost:8000
```

