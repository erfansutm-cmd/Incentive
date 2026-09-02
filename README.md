# Incentive

Starter project: **FastAPI** backend + **Vue 3 (Vite)** frontend, run with Docker Compose in both **development** and **production** modes.

## Structure

```
incentive/
├── docker-compose.yml           # development (default)
├── docker-compose.prod.yml      # production (standalone)
├── backend/                     # FastAPI
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
└── frontend/                    # Vue 3 + Vite
    ├── Dockerfile               # multi-stage: dev / build / prod (nginx)
    ├── nginx.conf               # prod: serves SPA, proxies /api → backend
    ├── package.json
    ├── vite.config.js           # dev: proxies /api → backend
    ├── index.html
    └── src/
        ├── main.js
        └── App.vue
```

## Database

The backend connects to MySQL using **SQLAlchemy + PyMySQL**. Connection
settings are read from environment variables (with dev defaults) and are
configured through a root `.env` file:

| Variable      | Default          |
|---------------|------------------|
| `DB_USER`     | `erfan.mohamadi` |
| `DB_PASSWORD` | *(empty)*        |
| `DB_HOST`     | `172.21.41.75`   |
| `DB_PORT`     | `3306`           |
| `DB_NAME`     | `incentive`      |

```bash
cp .env.example .env   # then fill in DB_PASSWORD
docker compose up --build
```

The connection lives in `backend/app/database.py` (SQLAlchemy engine, session
factory, and a `get_db` dependency). A readiness endpoint is available at
`GET /api/health/db`, which runs `SELECT 1` against MySQL and reports the
connection state.

## Development

```bash
docker compose up --build
```

- Frontend (Vite dev server): http://localhost:5173
- Backend API: http://localhost:8000 (docs at http://localhost:8000/docs)
- Hot reload on both sides — source folders are bind-mounted, `uvicorn --reload`
  and Vite pick up edits instantly.
- Vite proxies `/api/*` to the backend container (no CORS setup needed).

## Production

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

- App: http://localhost (port 80)
- The frontend is compiled (`vite build`) and served as static files by **nginx**.
- nginx proxies `/api/*` to the backend container — the backend is **not**
  exposed to the host directly.
- No bind mounts or reload; containers restart automatically (`unless-stopped`).

Stop production stack:

```bash
docker compose -f docker-compose.prod.yml down
```

## Dev vs prod at a glance

| | Development | Production |
|---|---|---|
| Compose file | `docker-compose.yml` (default) | `docker-compose.prod.yml` (`-f`) |
| Frontend | Vite dev server, HMR, port 5173 | Static build served by nginx, port 80 |
| Backend | `uvicorn --reload`, port 8000 exposed | `uvicorn`, internal only |
| Code mounts | Yes (live editing) | No (baked into images) |
| `/api` routing | Vite proxy | nginx proxy |

The frontend `Dockerfile` is multi-stage: dev uses the `dev` target,
production uses the `prod` (nginx) target.
