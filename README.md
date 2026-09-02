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
| `DB_CITIES_TABLE` | `cities`     |
| `DB_BUSINESS_ENTITIES_TABLE` | `business_entities` |
| `DB_CITY_MAPPING_TABLE` | `mafsho/city_mapping` |

```bash
cp .env.example .env   # then fill in DB_PASSWORD
docker compose up --build
```

The connection lives in `backend/app/database.py` (SQLAlchemy engine, session
factory, and a `get_db` dependency). A readiness endpoint is available at
`GET /api/health/db`, which runs `SELECT 1` against MySQL and reports the
connection state.

**Tables in other schemas.** Each table is set in the env as
`schema/table` (or just `table` for the default schema), e.g.

```
DB_CITIES_TABLE=cities
DB_BUSINESS_ENTITIES_TABLE=other_db/business_entities
DB_CITY_MAPPING_TABLE=mafsho/city_mapping
```

The `quote_table()` helper in `database.py` parses the `schema/table` form and
emits a safely quoted MySQL identifier (`` `other_db`.`business_entities` ``),
so a table can live in any database on the same MySQL server the DB user has
access to.

## Cities CRUD

The `cities` table is exposed through `backend/app/cities.py` (generic — it
introspects the table with `SHOW COLUMNS`, so it works with any schema). All
routes are under `/api/cities`:

| Method | Path           | Action                       |
|--------|----------------|------------------------------|
| GET    | `/api/cities`      | List all rows + column info |
| POST   | `/api/cities`      | Insert a new row           |
| PUT    | `/api/cities/{id}` | Update a row by PK        |
| DELETE | `/api/cities/{id}` | Delete a row by PK        |

Every route returns `{"status": "ok", "message": ...}` on success, or
`{"status": "error", "message": ...}` with a proper HTTP status on failure
(e.g. `404` if the table doesn't exist, `503` if the DB is unreachable).

The frontend page lives at `/cities` (`frontend/src/views/Cities.vue`): it
lists the table with all its columns and supports add / edit / delete with
confirmation popups, a green theme, and success/error toasts.

### City name lookup (auto-fill on "Add city")

The **Add city** form no longer needs every field typed by hand. Start typing a
city name and it is looked up in the city mapping table:

```sql
select distinct correct_city, correct_city_id, box_city_name, city_group
from mafsho.city_mapping
```

Picking a suggestion fills the matching columns of the `cities` table (the ID,
box city name and group) — the filled fields are shown locked, with an
*edit manually* link if you need to override one.

Suggestions come from the plain `select distinct …` rows, so **one entry per
city *and* box city name** — several cities can share the same box city name
and each of them stays addable. The only thing filtered out is the city
itself:

* **Already in the table** — any `correct_city` that is already a row of the
  cities table is left out (`NOT EXISTS` against the city-name column), so a
  city cannot be added twice, whatever its box city name. Typing its name
  shows "No match — either it is already in the table or it is missing from
  `city_mapping`".
* Add `?exclude_existing=0` to see the raw mapping rows, which is handy when a
  city you expect does not show up:
  `/api/cities/lookup?q=tehran&exclude_existing=0`.

| Method | Path                 | Action                                  |
|--------|----------------------|-----------------------------------------|
| GET    | `/api/cities/lookup` | Search the mapping table (`q`, `limit`) — cities already in the table are excluded |

The mapping table is set with `DB_CITY_MAPPING_TABLE` (default
`mafsho/city_mapping`) and follows the same `schema/table` convention as the
other tables. Because the cities table is introspected, the mapping columns are
matched to whatever the local columns are called — `correct_city` fills
`city_name` (or `city`), `correct_city_id` fills `city_id`, and so on; columns
with no match are simply skipped. If the mapping table is unreachable the form
stays fully usable, it just stops auto-filling.

## Business Entities CRUD

The `business_entities` table is exposed through
`backend/app/business_entities.py` under `/api/business-entities`:

| Method | Path                        | Action                    |
|--------|-----------------------------|---------------------------|
| GET    | `/api/business-entities`        | List all rows + columns |
| POST   | `/api/business-entities`        | Insert a new row        |
| PUT    | `/api/business-entities/{id}`   | Update a row by PK      |
| DELETE | `/api/business-entities/{id}`   | Delete a row by PK      |

The four JSON-array columns (`include_customer_id`, `exclude_customer_id`,
`include_delivery_category`, `exclude_delivery_category`) are parsed to real
arrays on read and serialized to JSON on write (a plain comma-separated
string is also accepted).

The frontend page lives at `/business-entities`
(`frontend/src/views/BusinessEntities.vue`). The JSON-array fields use a
tag-style input (`frontend/src/components/TagInput.vue`): pick a value from
the suggestion chips (known delivery categories, plus values already used in
the table) or type your own and press Enter / comma to add it — duplicates
are removed automatically.

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
