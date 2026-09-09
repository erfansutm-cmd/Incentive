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
| `DB_CITY_PLAN_MAPPING_TABLE` | `incentive/incentive_city_plan_mapping` |
| `DB_INCENTIVE_TYPE_TABLE` | `mafsho/incentive_type` |
| `DB_CITY_MAPPING_TABLE` | `mafsho/city_mapping` |
| `DB_DECISION_MATRIX_TABLE` | `incentive/incentive_decision_matrix` |
| `DB_ACTIVE_CITY_TABLE` | `incentive/incentive_active_city` |

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

| Method | Path                 | Action                                  |
|--------|----------------------|-----------------------------------------|
| GET    | `/api/cities/lookup` | Search the mapping table (`q`, `limit`) |

The mapping table is set with `DB_CITY_MAPPING_TABLE` (default
`mafsho/city_mapping`) and follows the same `schema/table` convention as the
other tables. Because the cities table is introspected, the mapping columns are
matched to whatever the local columns are called — `correct_city` fills
`city_name` (or `city`), `correct_city_id` fills `city_id`, and so on; columns
with no match are simply skipped. If the mapping table is unreachable the form
stays fully usable, it just stops auto-filling.

### Plans (slide-down per city)

Clicking a city row expands a slide-down panel with that city's rows from
`incentive.incentive_city_plan_mapping`, matched on `city_id`. The panel shows
the active mappings (`deactivated_at IS NULL`) first, with a
*Show deactivated* button to reveal the deactivated ones. The lookup lives in
`backend/app/city_plan_mappings.py` (separate from `cities.py`):

| Method | Path                 | Action                                  |
|--------|----------------------|-----------------------------------------|
| GET    | `/api/city-plan-mappings?city_id={id}[&include_deactivated=true]` | List mappings for one city |
| POST   | `/api/city-plan-mappings` | Add a mapping (`city_id`, `incentive_type_id`, `business_entity`) |
| POST   | `/api/city-plan-mappings/{id}/deactivate` | Deactivate a mapping (sets `deactivated_at`) |
| GET    | `/api/city-plan-mappings/{id}` | Get one mapping (plan detail page at `/plans/:id`) |
| GET    | `/api/incentive-types` | List incentive types (`id`, `name`) from `mafsho.incentive_type` |

The tables are set with `DB_CITY_PLAN_MAPPING_TABLE` (default
`incentive/incentive_city_plan_mapping`) and `DB_INCENTIVE_TYPE_TABLE`
(default `mafsho/incentive_type`); both follow the same `schema/table`
convention as the other tables.

In the panel, `incentive_type_id` is shown as its type name (e.g. `DAILY`),
the *Add plan* form picks the type from `mafsho.incentive_type` and the
business entity from `incentive.business_entities` (both are dropdowns —
nothing new can be added there), and every active row has
a *Deactivate* button behind a confirmation popup.

## Decision Matrix

Open **Decision Matrix** in the navigation or go to `/decision-matrix`. The
page manages the existing `incentive.incentive_decision_matrix` table through
`backend/app/api/decision_matrix.py`.

The hierarchy is **City group → Incentive type → Score type → Score steps**:

1. The first screen lists distinct, non-null/non-blank `city_group` values from
   `incentive.incentive_active_city`, even when the matrix is empty. Groups appear
   **one per line**: **Top 4**, then **tiers** (Tier 2 before Tier 10), then
   **Tehran**, then other groups. Top 4 matching ignores case and accepts spaces,
   underscores, or hyphens (e.g. `Top 4`, `top4`, `TOP_4`). Clicking a group slides
   its panel open **directly under that row**, keeping the group list on screen.
   Clicking it again collapses it; choosing another group closes the previous
   one. No page, route, or browser tab is opened by group selection.
2. Each configured incentive type has its own expandable panel. **Add incentive
   type** selects an existing `id`/`name` from `mafsho.incentive_type`, just like
   the Cities **Add plan** dropdown. The matrix's `incentive_type` column stores
   the **ID**, while the UI shows the **name**. Arbitrary incentive types cannot
   be added through the API, and the lookup table is never modified.
3. **Add incentive type** and **Add score type** use an in-page, keyboard-accessible
   dropdown for score types. Choose **Performance**, **Weather**, or **Order Level
   Increase**, or write a custom name and select **Use “…”**. The arrow opens the
   list; arrow keys and Enter choose an option; Escape closes the dropdown before
   closing the dialog. The table holds one row per step, so creating a type also
   saves its first step rather than an incomplete placeholder row.
4. The button reads **+ Add step**, without a number in parentheses. Inside the
   form, **Score** suggests `MAX(active score) + 1` in the selected city group,
   incentive type, and score type (or **1** if no steps are active). The **Score
   field is editable**: choose any unused positive whole number, including gaps
   or a previously deactivated score. The API rejects an already-active score
   with **409** and never silently substitutes another score.
5. `target_increase` and `pr_increase` are **required finite floats**. The form
   initially copies them from the nearest **active** step in the same
   group/incentive/score type, measured by absolute score distance; a tie picks
   the lower score. Changing the score updates untouched defaults. Manual values
   are preserved, and **Use its values** explicitly copies the current nearest
   step again. With no active neighbor, both fields start blank and must be filled.
   They cannot be null, even if the underlying table has nullable columns/defaults.
6. `control_bucket` is **null or a list of exactly three finite floats**. Leave
   all three inputs blank for null, or fill all three. A partial list, scalar,
   boolean, non-numeric member, NaN, or infinity is rejected. **Clear control
   bucket** restores null. Arrays are stored as JSON and decoded on read; the UI
   shows them as lists, e.g. `[0.1, 0.2, 0.3]`.
7. Existing steps have **no Edit action or update endpoint**. **Deactivate** asks
   for confirmation, then sets `deactivated_at = NOW()`. Deactivated steps remain
   in their own collapsible, read-only history table, never mixed into active
   steps. Neither table has a Status column. Deactivation does not delete or
   renumber old rows; a new row can reuse a deactivated score without changing
   its history.

Preset score types use fixed database/API values with separate UI captions:

| Database/API value | UI label |
|--------------------|----------|
| `performance` | Performance |
| `weather` | Weather |
| `order_level_increase` | Order Level Increase |

The dropdown, score-type panels, step form, and deactivation confirmation use the
friendly labels. New preset rows save the canonical database values, whether a
preset is selected or typed. Custom score-type names retain their spelling. Older
label-spelled presets are recognized as aliases for reads, score suggestions, and
duplicate detection without rewriting any existing history.

`id`, `created_at`, and `deactivated_at` are server-managed. The existing matrix
should have an auto-increment `id`, a positive-integer `score`, and nullable
`deactivated_at`. The expected columns are:

```
id, incentive_type, city_group, score_type, score,
target_increase, pr_increase, control_bucket, created_at, deactivated_at
```

**Value column storage:** `target_increase` and `pr_increase` need floating-point
or decimal columns (for example `DOUBLE NOT NULL`). `control_bucket` needs a
**nullable JSON or text column**, not a scalar numeric column, to store triples.
The API checks incompatible column types and returns an actionable error instead
of allowing a list or fractional value to be silently truncated. If your existing
schema differs, migrate it deliberately after reviewing any legacy null/scalar
values. No migration, data rewriting, seeding, or table creation is performed by
the app. Existing history remains readable and is never automatically rewritten.

Configure table names using the same `schema/table` convention used elsewhere:

```dotenv
DB_DECISION_MATRIX_TABLE=incentive/incentive_decision_matrix
DB_ACTIVE_CITY_TABLE=incentive/incentive_active_city
DB_INCENTIVE_TYPE_TABLE=mafsho/incentive_type
```

Both development and production Compose files pass these settings to the backend.
The city-group source is independent of `DB_CITIES_TABLE` and `DB_CITY_MAPPING_TABLE`.

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/decision-matrix/city-groups` | Distinct groups from active cities, independent of matrix contents |
| GET | `/api/decision-matrix?city_group={group}[&include_deactivated=true]` | Rows and metadata for one group; counts include history, suggested scores use active rows only |
| POST | `/api/decision-matrix` | Create a step with a chosen score (or default to the next active score), required target/PR floats, and an optional three-float bucket |
| POST | `/api/decision-matrix/{id}/deactivate` | Soft deactivate a step; repeated calls preserve its first deactivation timestamp |

Example creation payload (the group and incentive ID must exist in their lookups):

```json
{
  "city_group": "Top 4",
  "incentive_type": 1,
  "score_type": "performance",
  "score": 4,
  "target_increase": 0.15,
  "pr_increase": 0.05,
  "control_bucket": [0.1, 0.2, 0.3]
}
```

The UI retains the chosen score and reviewed values on a failed save, including
concurrent duplicate-score conflicts. Additions and deactivations share a MySQL
named lock and commit before releasing it, coordinating changes to the active
maximum and preventing duplicate **active** scores through this API. Writers
outside this API must coordinate separately. Table uniqueness constraints must
allow historical rows and a new active row to share a score; the API does not
change indexes or overwrite archived rows to achieve this.

### Decision Matrix tests

Backend tests run against an isolated SQLite fixture with attached schemas;
MySQL column introspection and lock functions are stubbed. They cover preset storage/display names,
suggested and custom scores, active-score uniqueness, lookup validation,
required floats, JSON triple round-trips, historical score reuse, deactivation,
and the named-lock lifecycle. They do **not** connect to the configured database.

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Browser tests use Playwright with intercepted API responses (no real database
writes). They cover inline city-group accordions, the custom score-type picker,
nearest-step prefill, editable creation scores, required float values, nullable
three-value buckets, concurrent changes, separate history, and mobile/keyboard behavior.

```bash
cd frontend
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
npm run build
```

The tests start Vite automatically, or reuse it when already running. An
existing Chromium installation can be used by setting
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.

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

## Performance score

`GET /api/performance/score/{city}/{business_entity}` exposes
`get_city_performance_score()` from `backend/app/core/performance_score.py`
(mirroring `GET /api/weather/score/{city}`):

```json
{ "city": "Tehran", "business_entity": "Food", "score": 4 }
```

The business entity's customer IDs are read from MySQL and their InSlot metrics
are read from ClickHouse; the rendered ClickHouse query, its timing, and row
counts are logged at INFO level. Missing data and unknown entities fall back
to score `1`. Blank `city` / `business_entity` values return `400`.
ClickHouse access uses `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT` (native protocol,
default `9000`), `CLICKHOUSE_DB`, `CLICKHOUSE_USER`, and
`CLICKHOUSE_PASSWORD`.

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
