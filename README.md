# SteamRecommender Monorepo

This repository is organized as a small monorepo:

- `frontend/` contains the Next.js app
- `backend/` will contain the FastAPI + LangChain API
- `supabase/` contains schema and migrations
- `data/` contains cleaned catalog assets
- `docs/` contains proposal and planning documents
- `archive/` keeps preserved pre-restructure artifacts

## Frontend local run

```bash
cd frontend
npm install
npm run lint
npm run dev
```

## Backend local run

```bash
cd backend
pip install -r requirements.txt
python -m compileall app
uvicorn app.main:app --reload
```

## Data and schema

- `data/games_clean.json`
- `data/all_tags.json`
- `supabase/migrations/`

## Notes

- `archive/` preserves the pre-restructure README, old Next API route, and old frontend-owned recommendation implementation.
- The frontend now talks to the backend via `NEXT_PUBLIC_BACKEND_URL`.
- The backend is a standard FastAPI app with no Docker, Celery, Redis, cron, or host-specific deployment config.
