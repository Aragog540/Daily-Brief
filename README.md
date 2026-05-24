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

## Auth (Supabase) setup

1. Create a Supabase project at https://app.supabase.com and copy the **Project URL**, the **anon/public key**, and the **service_role** key (keep the service key secret).

2. Create the `profiles` table (you said you've already run this):

```sql
create table if not exists public.profiles (
	user_id text primary key,
	email text,
	city text,
	created_at timestamptz default now()
);
```

3. (Optional) If you want the frontend (anon key) to read/update the `profiles` table directly, enable Row Level Security and add policies. See `migrations/001_create_profiles.sql` for an example [...]

4. Set environment variables locally:

Backend (.env or PowerShell):
```
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key_here
OPENWEATHER_API_KEY=your_openweather_key_here
GROQ_API_KEY=your_groq_key_here
USE_OPEN_METEO=false
```

Frontend (`frontend/.env`):
```
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_public_key_here
VITE_API_URL=http://localhost:8000
```

5. Run locally and test:

Backend (same session where env vars are set):
```bash
uvicorn backend.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

6. In the frontend UI: sign in via the Auth component (magic link), open the email, click the link, then set your city in the Profile prompt. The app will save your city to Supabase and use it au[...]

If you want, I can add a small migration runner or a CI step to apply `migrations/001_create_profiles.sql` automatically for you.

