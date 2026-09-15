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
| `DB_INCENTIVE_BASE_CONFIG_TABLE` | `incentive/incentive_base_configs` |
| `DB_INCENTIVE_BASE_CONFIG_LOG_TABLE` | `incentive/incentive_base_configs_logs` |
| `DB_INCENTIVE_PLANS_TABLE` | `incentive/final_incentive_plans` |

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

### Base configs of a plan (per-plan allocators)

The *Details* button of a plan opens `/plans/:id`
(`frontend/src/views/PlanDetail.vue`). Under the plan's facts it lists that
plan's rows of `incentive.incentive_base_configs`, joined on `plan_id` = the
plan's primary key, through `backend/app/api/incentive_base_configs.py`:

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/incentive-base-configs?plan_id={id}[&include_deactivated=true]` | Base configs (allocators) of one plan |
| POST | `/api/incentive-base-configs` | Add an allocator to a plan |
| PUT | `/api/incentive-base-configs/plan/{id}` | Change `listing_id` / `duration` for **every** allocator of a plan |
| PUT | `/api/incentive-base-configs/{id}` | Change one allocator in place; the row as it was is logged first |
| POST | `/api/incentive-base-configs/{id}/deactivate` | Set `deactivated_at = NOW()`; the row is logged first |
| POST | `/api/incentive-base-configs/{id}/activate` | Clear `deactivated_at` to bring a row back; the row is logged first |
| GET | `/api/incentive-base-configs/{id}/logs` | Logged previous versions of one config, newest first |

The table is set with `DB_INCENTIVE_BASE_CONFIG_TABLE` (default
`incentive/incentive_base_configs`) and follows the same `schema/table`
convention. The expected columns are:

```
id, plan_id, listing_id, allocator_id, rule_name, impact_ratio,
duration, districts, vendors, batch_size, clustering_method,
sensitivity_id, sensitivity_group, created_at, updated_at, deactivated_at
```

Rows come back ordered by `listing_id`, then `impact_ratio` descending, then
`id`, so a listing's dominant allocator leads and its allocators stay adjacent.
The response also carries `columns`, `summary_columns`, `total`,
`active_count`, `deactivated_count` and `impact_ratio_sum` (a plan's *active*
allocators normally add up to `1`; deactivated rows and rows without a ratio
are left out of the sum).

### The impact ratios have to add up to 100%

The section header shows the share as a pill. When a plan's active allocators
add up to `1` it reads `impact 100%`; any other total turns the pill **red** and
puts a standing line under the table saying how far off it is — *The impact
ratios of this plan's active allocators add up to 115%, not 100% — 15% too
much.* Every change that leaves a plan off 100% repeats that message in its own
toast, so adding, editing and deactivating an allocator each flag it at the
moment it happens rather than only on a later visit. A rounding-sized
difference (under 0.005%) is treated as exact and not reported.

### Every allocator of a plan shares one listing

`listing_id` is a plan-level value, so all of a plan's allocators must carry the
same one. The section re-checks this on every load and after every change, from
the rows it just fetched: if the **active** allocators disagree, the header shows
a red `N listings` pill and a standing line naming them — *This plan's active
allocators use 2 different listings (kerman-daily-foodZooket,
tehran-daily-foodZooket), but a plan has only one.* — and the same message rides
along in the toast of any write. Writes already refuse to split a plan (a
per-row `listing_id` is a 409, and adding inherits the plan's listing), so this
catches rows that got out of step some other way, such as a direct database
edit. Deactivated rows are left out, since they are not part of the plan's
active split.

The UI shows only three fields up front — **Allocator ID**, **Rule name**,
**Impact ratio** (as a percentage with the raw value beside it) — and keeps the
rest of the row (`id`, `districts`, `vendors`, `batch_size`,
`clustering_method`, `sensitivity_id`, `sensitivity_group`, `created_at`,
`updated_at`, `deactivated_at`) behind each row's dropdown. `plan_id`,
`listing_id` and `duration` are not repeated on every allocator: the plan is the
plan, and the other two are shown once in the strip above the table. Clicking
the row (or its chevron) opens that dropdown; *Expand all* / *Collapse all* does
it for every allocator at once. Which fields are hidden follows the table's real
columns, so an added column appears in the dropdown without a code change, and a
missing one simply disappears. Columns ending in `_at` are rendered as readable
dates (`Sep 14, 2026, 10:11 AM`), never as raw ISO strings.

`districts` and `vendors` hold a JSON list of strings, and that JSON can contain
`null`s. Both are shown as chips rather than as raw `["Sadra",null]`, the nulls
are dropped, and an empty or missing list reads as `—`. The same applies inside
a logged previous version.

Deactivated configs are left out of the list until *Show deactivated (N)* is
pressed; they then join the table greyed out, with a *Deactivated* tag, while
the allocator count and the impact share keep describing the active rows. A
deactivated row cannot be edited, but it can be brought back: its **Activate**
button calls `POST /{id}/activate`, which logs the row as it was, clears
`deactivated_at` and refreshes `updated_at`. Because every change is logged,
re-activating keeps the same `id` and the whole history — including the
deactivation — stays attached to the row. Activating a row that is already
active changes nothing and logs nothing.

The section loads independently of the plan itself: if the lookup fails (for
example the table does not exist yet) the plan facts stay on screen and the
section offers a *Retry*. A plan with no rows shows an empty state.

### Listing and duration belong to the plan, not to a row

`listing_id` and `duration` are the same on every allocator of a plan, so the UI
shows them once, in a strip above the table, and edits them once: **Edit for
all** opens a popup whose save calls `PUT /api/incentive-base-configs/plan/{id}`.
The endpoint updates every **active** row of the plan, logs each row's previous
values first, and does it all in one transaction; rows that already hold the new
values are left alone and not logged. Deactivated rows are never rewritten, so
history keeps the listing they had. Any other field sent to that endpoint is
rejected with 400 — per-allocator fields are changed per allocator.

Adding an allocator inherits the plan's listing and duration. Only the first
allocator of a plan sets them (and its form asks for them); afterwards a payload
carrying different ones is rejected with **409** and the `conflicts` that caused
it, so a plan can never end up half-migrated.

### Changing one allocator

Per-allocator fields (`allocator_id`, `rule_name`, `impact_ratio`, `districts`,
`vendors`, `batch_size`, `clustering_method`, `sensitivity_id`,
`sensitivity_group`) are changed in place by `PUT /{id}`, which writes the row
as it was to the log table first — the log is what preserves the previous
version, so the row keeps its `id` and its history stays attached to it. The
whole thing is one transaction: if the update fails, no log row is left behind.
A payload that changes nothing writes no log row. `plan_id` and the plan-shared
`listing_id` / `duration` are not settable here; sending one is rejected with
**409** pointing at the plan-level endpoint, so a plan cannot be split one row
at a time.

In the form, **Allocator ID**, **Rule name** and **Impact ratio** are marked
*required* and the rest *(optional)* — the same in the add and the edit popup.
`districts` and `vendors` are edited as a list: type a value and press Enter (or
comma) to add it, × to remove one, and an emptied list is stored as no value at
all rather than as `[]`. Each row also has its own **Deactivate** button behind
a confirmation.

Two fields are not plain text boxes:

- **Clustering method** is a combo (`frontend/src/components/FreeCombo.vue`). It
  offers the two methods in use — `kmeans` and `rfmxs` — and opening it always
  shows the whole list, so a method already stored can be switched without
  clearing it first. Anything typed is just as valid: unlisted text is offered
  back as *Use "…"* and stored as-is, because the column is free text and a new
  method should not need a code change. A value that is not on the list (an
  older row's `dbscan`, say) still displays and edits normally.
- **Sensitivity group** is three boxes (`FloatTriple.vue`), one per group. The
  column holds a JSON array of exactly three floats, so the form only ever
  sends all three or nothing: filling one or two is refused with *'Sensitivity
  Group' needs all three groups, or none.* and a non-numeric entry with
  *…groups must be numbers.* Clearing all three stores no value at all. Read
  back in a row's dropdown it renders as `G1 0.1 · G2 0.2 · G3 0.3` rather than
  as raw JSON.

### Available allocators, rules and listings

The forms pick from what the incentive services actually have, through
`backend/app/api/incentive_lookups.py`. The browser never calls those services
directly — these endpoints proxy them over the same origin, normalize whatever
shape they answer with into a plain list of names, filter on `q` and cap at
`limit`:

| Method | Path | Upstream |
|--------|------|----------|
| GET | `/api/incentive-lookups/allocators?q=&limit=` | `ALLOCATOR_NAMES_URL` |
| GET | `/api/incentive-lookups/rules?q=&limit=` | `RULE_NAMES_URL` |
| GET | `/api/incentive-lookups/listings?q=&limit=` | `LISTING_QUERIES_URL` |

```dotenv
ALLOCATOR_NAMES_URL=http://172.21.88.174:5000/allocator/names
RULE_NAMES_URL=http://172.21.88.174:5000/rules/names
LISTING_QUERIES_URL=http://172.21.88.148:5000/queries/all
```

Listings come from one endpoint for every city (`/queries/all`), so the listing
field offers all of them. The normalizer accepts a bare list of strings, or
objects under `names`, `data`, `results`, `result`, `items`, `rows`, `response`,
`queries`, `allocators`, `rules` or `listings`, and reads each entry's `name`,
`id`, `value`, `label`, `title`, `query`, `allocator`, `rule` or `listing` key.
An unreachable or erroring service answers **502** naming the service.

Listing, allocator and rule are **selects, not free text**: typing narrows the
offered names, but only picking one sets the value, so a row can never hold a
name the service does not have. The chosen name has a **×** to clear it again.
If a lookup is down the field says *lookup unavailable — the list cannot be
loaded* and stays empty rather than accepting something invented.

### Change log (previous version before every change)

`incentive.incentive_base_configs_logs`, set with
`DB_INCENTIVE_BASE_CONFIG_LOG_TABLE`, holds the row as it was *before* a change:

```
log_id, config_id, plan_id, listing_id, allocator_id, rule_name, impact_ratio,
duration, districts, vendors, batch_size, clustering_method,
sensitivity_id, sensitivity_group, created_at, updated_at, deactivated_at,
changed_at
```

Every `PUT` and every deactivation copies the current row into the log table
(`config_id` = the config's id, `changed_at` = `NOW()`, `log_id`
auto-incremented) and applies the change **in the same transaction**, so a
failed update leaves no orphan log row and no unlogged change. Only columns
the log table really has are copied, so a column added to both tables is
logged without a code change.

- A `PUT` whose values are all unchanged writes **no** log row and answers
  `{"logged": false, "message": "No changes to record."}`; a real change
  answers with the `log_id` and a `changes` map of `{field: {from, to}}` using
  the stored values (`0.4` and `"0.4000"` count as equal).
- `created_at`, `updated_at`, `deactivated_at` and `plan_id` are not settable
  through `PUT`. `updated_at` is stamped with `NOW()` by the server;
  deactivation and re-activation go through their own endpoints. Deactivating an
  already deactivated config — or activating an already active one — changes
  nothing and logs nothing.
- **Writes need the log table to exist.** If it is missing the request fails
  with its name in the message and the config is left untouched, rather than
  silently losing history. Reads work without it — the page shows the error
  inside the row instead.

In the UI each row's dropdown has a **Change history** disclosure: it fetches
that config's log rows on first open (nothing is requested before) and lists
them newest first, each with its `changed_at` and the full previous row
(`log_id`, `config_id` and `changed_at` are not repeated as fields). A failed
history lookup offers a *Retry* and never affects the rest of the page.

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
   field is editable**: choose any unused whole number of **0 or more**,
   including gaps or a previously deactivated score — a series may start at
   score 0, and 0 occupies its slot like any other score. The API rejects an
   already-active score with **409** and never silently substitutes another
   score.
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
7. Every active step has **Edit** and **Deactivate**. Edit is **one action that
   keeps the history complete**: the row being edited is deactivated and a new
   active row with the corrected values is added, in the same locked
   transaction — rows are never updated in place, and the **score never
   changes**. **Deactivate** asks for
   confirmation, then just sets `deactivated_at = NOW()`. Deactivated steps
   remain in their own collapsible, read-only history table, never mixed into
   active steps. Neither table has a Status column. Deactivation does not delete
   or renumber old rows; a new row can reuse a deactivated score without changing
   its history.

### Editing a step

`POST /api/decision-matrix/{id}/edit` is deliberately **not** an update: it
archives the row and inserts its replacement. The row being edited is set to
`deactivated_at = NOW()` and a new row with the submitted `target_increase`,
`pr_increase` and `control_bucket` is inserted, both inside the same named-lock
transaction that an addition uses. So:

- history stays complete — the previous version is still there, with its own
  `created_at`, and is never rewritten;
- a half-finished edit is impossible: if anything fails (validation, the lock),
  the original row stays active and nothing is inserted;
- **the score is fixed**: it identifies the step inside its series, so the new
  row keeps the same score and sending `score` is a `400`. `city_group`,
  `incentive_type` and `score_type` are fixed the same way. An edit changes the
  values of a step, never which step it is;
- a deactivated row cannot be edited (`409`), and an unknown id is a `404`.

The response carries the new row (`row`) and the id it replaced (`replaced_id`).
In the UI, **Edit** opens a form prefilled from the row: target increase, PR
increase and the three-value control bucket, with the score shown read-only next
to *stays the same — editing changes the values, not the step's score*. The form
shows what saving will do (*Score 3 → deactivated · score 3 active again with the
new values*), refuses a no-op save (nothing changed → the button stays disabled,
so no identical duplicate is created), and an error from the API keeps the form —
with the values entered — open. After a successful save the edited series'
history is revealed, so the archived row and the new one are both visible. The
same form is used on the main page and on the per-type page
(`/decision-matrix/type`).

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
should have an auto-increment `id`, a non-negative integer `score` (0 is
valid), and nullable `deactivated_at`. The expected columns are:

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
| POST | `/api/decision-matrix/{id}/edit` | Edit a step's values in one action: deactivate it and add a new active row with the same score |
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

Frontend component tests run in jsdom against a mocked `/api`
(`frontend/tests/unit/`, `frontend/tests/unit/api-mock.js`), so they need no
browser, no backend and no database:

```bash
cd frontend
npm ci
npm test          # one run
npm run test:watch
```

They mount the real `PlanDetail.vue` and cover the plan-level listing/duration
strip, that `plan_id` / `listing_id` / `duration` stay out of a row, the
select-only lookup fields (typing filters but never becomes a value), in-place
edits with their logged previous values, required vs optional markers, list
columns as chips and as a tag editor, deactivation behind a confirmation,
re-activating a deactivated row, the impact share turning red and saying how far
off it is whenever a change leaves a plan away from 100%, the clustering-method
combo accepting both a listed and a typed method, the three sensitivity groups
being all-or-none, add-allocator inheritance, lookup outages, write failures,
change history and its retry, and the empty/error states. The Final Decisions
tab has its own file (`frontend/tests/unit/final-decisions.spec.js`): the plan
summary of a collapsed city, the plan cards, the plan-type-order popup and the
plans-unavailable state.

Browser tests use Playwright with intercepted API responses (no real database
writes). They cover inline city-group accordions, the custom score-type picker,
nearest-step prefill, editable creation scores, required float values, nullable
three-value buckets, concurrent changes, separate history, mobile/keyboard
behavior, and the same plan-detail flows end to end.

```bash
cd frontend
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
npm run build
```

The tests start Vite automatically, or reuse it when already running. An
existing Chromium installation can be used by setting
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. Playwright's `testDir` is `tests/` and it
ignores `tests/unit/`, so the two suites never pick each other up.

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

## Final Decisions

Open **Final Decisions** in the navigation or go to `/final-decisions`. The tab
answers `GET /api/final-decisions?incentive_date=YYYY-MM-DD` (default: tomorrow)
from `backend/app/api/final_decisions.py` and puts the two halves of the daily
decision on one screen.

**Scores.** Every city of `incentive.incentive_active_city` that has rows in
`incentive.incentive_scores` on that date gets a line, one per business entity.
The collapsed row shows the entity that comes first in the **Entity order**
popup (`foodZooket > food > Zooket > others`, alphabetical inside a level);
expanding a city reveals all of its entities. Score badges are colored from
green (lowest) to red (highest) per score type, and the columns sort by
performance, order-level increase and weather.

**Plans.** The rows of `incentive.final_incentive_plans` of the same date, joined
to `incentive.incentive_city_plan_mapping` on
`plan_mapping_id = incentive_city_plan_mapping.id` — that join supplies the
`city_id`, the `incentive_type_id` and the `business_entity` of every plan, and
`mafsho.incentive_type` supplies the type **name**, exactly the way the Cities
tab shows it. Per plan the tab shows:

| Field | Where it comes from | How it is shown |
|---|---|---|
| Incentive type | `mafsho.incentive_type.name` (via `incentive_type_id`) | Type name, with `#id` next to it |
| Business entity | `incentive_city_plan_mapping.business_entity` | Under the type name |
| Target change | `final_incentive_plans.target_change` | `1.000` (three decimals) |
| PR change | `final_incentive_plans.pr_change` | `1.100` (three decimals) |
| Control bucket | `final_incentive_plans.control_bucket` | `[0.2, 0.2, 0.1]` decoded into chips, like the Decision Matrix |
| Updated at | `updated_at` / `updated_by` | `15 Sep 2026, 13:17 · System` |
| Plan page | `plan_mapping_id` | *Details* opens `/plans/{plan_mapping_id}` in a new tab |

A city with several plans shows the first one in the collapsed row (type, entity,
target/PR/bucket, updated at) plus a `+N more` pill; expanding the city lists
every plan as a card, and even the collapsed row keeps the scores next to it.

### Plan order (top first)

Plans of a city are listed by incentive type, top first: `default` → `DAILY` →
`ON-TOP-FOOD` → the rest alphabetically, so the plan that matters most is the one
summarized in the collapsed row and the one wearing the **top** badge in the
expanded panel. The order comes from `FINAL_DECISION_PLAN_TYPE_ORDER` (comma
separated type names, anything unlisted follows alphabetically) and is returned
as `plan_type_order`.

The **Plan type order** button opens a popup that reorders it — drag a row, use
its ↑ / ↓ buttons, *Add all* for types that are not in the list yet, or
*Reset to default* to go back to the configured order. The table follows the
popup immediately, and the choice is remembered in the browser
(`localStorage`, `frontend/src/lib/storedOrder.js`) so a reload keeps it;
*Reset to default* clears it again. The same popup component
(`frontend/src/components/OrderEditor.vue`) drives the **Entity order** button,
so both orders behave identically.

A plan whose mapping row is deactivated is still shown, flagged **mapping off**,
instead of disappearing silently. Plans belonging to another incentive date are
not mixed in.

### When the plans table cannot be read

Plans are best effort, so a missing or unreachable `final_incentive_plans` table never
hides the scores: the cities and their scores still render, the *Plans* panel
says what went wrong and offers a **Retry**, the collapsed rows read
*Plans unavailable*, and the response carries the message in `plans_error`
alongside `total_plans` and `plan_type_order`.

Plans of a city that has no scores on the date have no row to live under. They
are not dropped silently either: the response counts them in
`plans_without_scores`, names their cities in `plans_without_scores_cities`, and
the tab shows a notice above the table.

### Final Decisions tests

`backend/tests/test_final_decisions.py` runs the endpoint SQL against an isolated
SQLite store with attached `incentive` / `mafsho` schemas, so the plan join, the
type-name lookup, the date filter, the bucket decoding and the ordering are all
exercised for real. It also covers the graceful *plans table missing* path.
`frontend/tests/unit/final-decisions.spec.js` mounts the real view against a
mocked `/api` and covers the collapsed-row summary, the plan cards, the
type-order popup (reorder and reset) and the empty/error states.

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
