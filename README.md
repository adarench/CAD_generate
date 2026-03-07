# Utah Subdivision Studio

Utah Subdivision Studio is a parcel-driven land feasibility demo built around the existing `ai_subdivision` optimization engine. The current stack includes:

- live Utah parcel lookup against UGRC ArcGIS parcel services
- county-scoped APN search and map-click parcel selection
- canonical parcel normalization before planning
- FastAPI optimization and export APIs
- PostgreSQL/PostGIS-ready persistence for parcels, runs, results, and parcel sources
- Next.js planner and saved-run UI
- DXF, STEP, and GeoJSON exports for every saved run

## Monorepo Layout

```text
ai_subdivision/          Geometry engine, street networks, yield optimization
apps/python-api/         FastAPI parcel + optimization API, DB persistence, export serving
apps/web/                Next.js parcel map, planner workspace, run history UI
apps/python-api/db/      PostGIS schema
apps/python-api/data/    JSON fallback cache + generated export artifacts
```

## Environment

Copy `.env.example` to `.env` and adjust if needed:

```bash
cp .env.example .env
```

Key variables:

- `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/subdivision`
- local PostgreSQL also works, e.g. `postgresql://arench@127.0.0.1:54329/subdivision`
- `PUBLIC_API_BASE_URL=http://127.0.0.1:8000`
- `PYTHON_API_URL=http://127.0.0.1:8000`

## Database Bootstrap

### Option A: Docker / PostGIS container

```bash
docker compose up -d postgis
```

The schema is mounted from [apps/python-api/db/schema.sql](/Users/arench/Desktop/Architecture_test/apps/python-api/db/schema.sql).

### Option B: Local PostgreSQL

If PostgreSQL is already running locally, create the DB and apply the schema:

```bash
createdb subdivision
psql "$DATABASE_URL" -f apps/python-api/db/schema.sql
```

If PostGIS is not installed yet, install it first for your local PostgreSQL distribution.

## Backend

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -r apps/python-api/requirements.txt
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/subdivision \
PUBLIC_API_BASE_URL=http://127.0.0.1:8000 \
python3 -m uvicorn main:app --app-dir apps/python-api --host 127.0.0.1 --port 8000
```

### Backend routes

- `GET /api/health`
- `GET /api/parcels/search?county=Salt%20Lake&apn=12345678`
- `GET /api/parcels/by-click?county=Salt%20Lake&lng=-111.89&lat=40.30`
- `GET /api/parcels/{parcelId}`
- `GET /api/parcels/recent`
- `POST /api/optimize`
- `GET /api/runs`
- `GET /api/runs/{runId}`
- `GET /exports/{runId}/{filename}`

## Frontend

```bash
npm install --prefix apps/web
PYTHON_API_URL=http://127.0.0.1:8000 npm run dev --prefix apps/web
```

Open:

- `http://127.0.0.1:3000/`
- `http://127.0.0.1:3000/map`
- `http://127.0.0.1:3000/planner/<parcelId>`
- `http://127.0.0.1:3000/runs`

## Product Workflow

### Map intake

- open `/map`
- choose a Utah county
- search by APN or click the map
- review the normalized parcel drawer
- open the planner

### Planner

- adjust frontage, depth, min area, road width, easement width, and target lots
- select topology preferences and strict mode
- run optimization
- review summary, candidate breakdown, and exports
- open the saved run

### Saved runs

- view `/runs`
- reopen `/runs/[runId]`
- inspect geometry, input constraints, topology results, and export links

## Live Parcel Integration

The backend ArcGIS client lives in [apps/python-api/services/arcgis_parcel_client.py](/Users/arench/Desktop/Architecture_test/apps/python-api/services/arcgis_parcel_client.py). It queries official UGRC parcel feature services such as:

- `https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_SaltLake/FeatureServer/0`

The client normalizes the ArcGIS payload into the canonical parcel schema and caches the result in Postgres or the local JSON fallback if the database is unavailable.

## Validation

Validated locally during development:

- `python3 -m py_compile apps/python-api/main.py apps/python-api/schemas.py apps/python-api/services/*.py ai_subdivision/*.py`
- `npm run build --prefix apps/web`
- `GET /api/health` returns `{"status":"ok"}`
- live APN lookup for Salt Lake County parcel `22282760130000`
- live map-click parcel lookup near `(-111.83684683892612, 40.61985292120375)`
- PostGIS parcel cache verified with SQL row counts
- live optimize request saved run `e132edc2-8288-41f8-9551-a4e3d40a9629`
- saved run fetch returning stored geometry and metadata
- DXF / STEP / GeoJSON export files created under `apps/python-api/data/exports/<runId>/`
- frontend pages served locally on port 3000 with HTTP 200 for `/`, `/map`, `/planner/[parcelId]`, and `/runs/[runId]`
- Next.js proxy routes verified for parcel search, run history, and optimization

The product keeps a JSON fallback cache for development, but the verified path above used a live PostGIS-backed PostgreSQL instance on port `54329`.
