# Event Search

Upload a `.tgz` archive of event logs once, then search the imported events by **any one or any combination of the 15 event fields**. Django REST Framework backend, React + TypeScript (Vite) frontend, SQLite storage, Docker Compose packaging.

## Features

- One-step `.tgz` upload from the UI (progress bar, import summary: files, records imported / duplicate / invalid, messages).
- Safe archive handling: gzip/tar validation, size limits, path-traversal / absolute-path / symlink rejection, zip-bomb guard. Members are streamed into the parser and **never written to disk under archive-supplied names**.
- Batched, transactional import (all-or-nothing); duplicate protection for re-uploads and for overlapping archives.
- Search on all 15 fields (AND semantics), validated on client and server, paginated with a total count, deterministic order, and a server-measured search time.
- Source filename retained per event and shown in every result row.
- Health, ingestion-status and dataset-summary endpoints.
- Backend (38) and frontend (17) automated tests; Dockerfiles + Compose.

## Architecture and data flow

```
Browser ──► nginx (frontend container, :8080)
              ├─ static React build
              └─ /api/*  ──► gunicorn + Django REST Framework (backend container)
                                  ├─ POST /uploads   → archive_service → ingestion_service → SQLite
                                  └─ GET  /events    → search_service  → indexed SQLite query
```

The browser only ever talks to same-origin `/api/v1` (Vite proxy in development, nginx in Docker), so there is no CORS configuration and no `localhost` hard-coded in the frontend bundle. `VITE_API_BASE_URL` can override the base URL at build time.

Backend modules (`backend/events/`): `models.py`, `fields.py` (single source of truth for the 15 fields), `views.py`, `serializers.py`, `urls.py`, `exceptions.py`, and `services/` → `archive_service.py` (upload storage + safe reading), `parser_service.py`, `ingestion_service.py`, `search_service.py`. Upload/ingestion and search share only the model and the field validators.

## Technology choices

| Choice | Why |
|---|---|
| **SQLite** (WAL mode) | The supplied archive is 676 files / 103,520 lines → 100,000 unique events (~20 MB database). That is far below the size where PostgreSQL helps; SQLite gives sub-4 ms indexed queries with zero extra infrastructure. Switching to PostgreSQL only requires changing `DATABASES` (the code uses plain ORM queries). |
| Synchronous import | Importing the real archive takes ~17 s on a dev laptop (see below), so a background queue (Celery/Redis) was not justified. Gunicorn and nginx timeouts are raised to 900 s accordingly. |
| Django ORM `.values()` | Search returns plain dicts, avoiding model instantiation for up to 200 rows. |
| No Redis/Celery/Elasticsearch | Not needed — measured latency is already low. |

## Prerequisites

- Docker workflow: Docker with Compose v2.
- Local development: Python 3.11+ and Node 18+.

## Run with Docker Compose

```bash
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
                              # then edit DJANGO_SECRET_KEY (see the comment in the file)
docker compose up --build -d
docker compose ps             # wait until backend and frontend are "healthy"
```

Open <http://localhost:8080> (`FRONTEND_PORT` in `.env` changes the port). Startup order: a one-shot `migrate` service applies migrations → `backend` starts (healthchecked via `/api/v1/health/`) → `frontend` (nginx) starts after the backend is healthy.

Data (SQLite file and the stored archives) lives in the named volume `event_data` (`/data` in the backend container) and survives `docker compose down`. `docker compose down -v` deletes it.

### Uploading the supplied archive

1. In the UI click **Upload .tgz archive** and choose `events.tgz`. The import takes roughly 20–40 s; the page shows the summary when done.
2. Alternative (CLI): put the archive at `data/events.tgz` (this folder is git-ignored and outside both Docker build contexts) and run
   ```bash
   docker compose run --rm backend python manage.py import_archive /seed/events.tgz
   ```

Re-uploading the same file reports "Already imported" and changes nothing.

## Local development

Backend (bash; PowerShell users: `$env:DJANGO_DEBUG="true"`, and `.venv\Scripts\python`):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.lock.txt
export DJANGO_DEBUG=true                                  # allows the built-in dev secret key
python manage.py migrate
python manage.py runserver 8000
```

Frontend (second terminal; Vite proxies `/api` to `127.0.0.1:8000`, override with `VITE_DEV_PROXY_TARGET`):

```bash
cd frontend
npm ci
npm run dev                  # http://localhost:5173
```

Without `DJANGO_DEBUG=true` the backend refuses to start unless `DJANGO_SECRET_KEY` is set. Local data goes to `backend/data/` (override with `DATA_DIR`).

## Tests and checks

```bash
# backend (38 tests, uses a throw-away test database and temp upload dirs)
cd backend && DJANGO_DEBUG=true python manage.py test

# frontend (17 tests), lint, type check, production build
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

Backend tests cover: valid/malformed record parsing, valid and invalid archives, path-traversal/symlink/oversize rejection, filename preservation, each of the 15 fields searched individually, AND combinations, blank filters, invalid/unsupported parameters, counts and pagination, search-time fields, repeated and overlapping uploads, rollback on mid-import failure, empty datasets/no matches, and JSON error handling. They use small synthetic archives only. Frontend tests (Vitest + Testing Library, `fetch`/XHR stubbed) cover all 15 inputs, single and multi-field search, results with filename, time and count, pagination preserving the submitted filters, uploads (success, duplicate, failure, wrong extension), empty results and API/network errors.

## API (`/api/v1`)

All errors are JSON: `{"detail": "...", "errors": {"<field>": ["..."]}}` (the `errors` key appears for validation errors).

| Method & path | Purpose |
|---|---|
| `GET /health/` | `{"status":"ok"}` (200) or 503 if the DB is unreachable |
| `POST /uploads/` | multipart field `file` (`.tgz` / `.tar.gz`). **201** imported · **200** identical archive already imported (`"duplicate": true`) · **400** not a valid/safe archive or bad request · **409** same archive currently importing · **413** over `MAX_UPLOAD_BYTES` · **422** readable archive containing no valid events |
| `GET /events/` | search (below) |
| `GET /ingestions/`, `GET /ingestions/<id>/` | ingestion status / summaries |
| `GET /summary/` | total events, distinct source files, latest ingestion |

Example:

```bash
curl -F "file=@events.tgz" http://localhost:8080/api/v1/uploads/
curl "http://localhost:8080/api/v1/events/?srcaddr=159.62.125.136&dstport=23475&page=1&page_size=50"
```

```json
{
  "count": 1, "page": 1, "page_size": 50, "total_pages": 1,
  "search_time_ms": 0.912, "search_time_seconds": 0.000912,
  "results": [{
    "serialno": "1", "version": "2", "account-id": "348935949", "instance-id": "eni-293216456",
    "srcaddr": "159.62.125.136", "dstaddr": "30.55.177.194", "srcport": 152, "dstport": 23475,
    "protocol": 8, "packets": 10, "bytes": 3929334, "starttime": 1725850449, "endtime": 1725855086,
    "action": "REJECT", "log-status": "OK", "file": "xaa"
  }]
}
```

(`file` is the base name of the log file inside the archive; the supplied archive's files are named `xaa`…`xzz`.)

### Field types and search semantics

Query-string names equal the field names. Identifiers are strings (`serialno`, `version`, `account-id`, `instance-id`); addresses are strings; `srcport`, `dstport`, `protocol`, `packets`, `bytes`, `starttime`, `endtime` are integers.

- Supplied non-blank filters are combined with **AND**; blank / whitespace-only filters are **ignored**.
- **An empty search (no non-blank filter) is rejected with 400** rather than returning the whole dataset.
- All matching is **exact**. `action` and `log-status` are case-insensitive (values are upper-cased at import and in queries, so they stay indexable). `instance-id` is case-sensitive. IPs are compared in canonical form.
- Validation: `serialno`/`version`/`account-id` digits only; numeric fields non-negative integers (ports and protocol are bounded only by a 32-bit int because the supplied data contains ports up to 102400); IPs must be valid IPv4/IPv6. Unsupported parameter names, repeated parameters and invalid `page` / `page_size` (1–200, default 50) return 400. A page past the end returns an empty `results` with the real `count`.
- Order is by insertion id, so paging is deterministic and complete.

## Log format and ingestion

Observed format: plain text, **no header, single space delimiter**, one event per line, 15 values in the order of the field list. The parser splits on any whitespace, accepts an optional header line, and treats `-` as NULL (flow-log style). Lines with the wrong field count or invalid values are counted as invalid, reported (first 50 messages kept) and skipped; the rest of the archive is still imported.

Findings on the supplied archive: 676 files, 103,520 lines, **100,000 unique serial numbers; 3,520 lines are exact repeats of events in other files**.

- **Duplicate handling:** `serialno` is unique. A line whose serial already exists (earlier in the same archive or from a previous upload) is skipped and counted as a duplicate; the first occurrence (and its filename) wins. Separately, each archive is identified by its SHA-256; identical bytes are never re-processed.
- **Atomicity:** the whole import runs in one transaction; any failure rolls everything back and the ingestion row is marked `failed` (the same file can be retried).
- **Memory:** archives are streamed; rows are inserted in batches of 2,000 (`INGEST_BATCH_SIZE`).
- Unsafe members (absolute/`..` paths, links, devices) reject the archive; hidden (`._*`), empty and binary files are skipped and reported.
- After a successful import `ANALYZE` refreshes SQLite's statistics. Stored archives are kept as `/data/uploads/<sha256>.tgz`.

## Schema and indexes

`Event`: the 15 fields (+ `source_file`, an auto `id`). `serialno` has a unique index. Single-column indexes: `account_id`, `instance_id`, `srcaddr`, `dstaddr`, `srcport`, `dstport`, `packets`, `bytes`, `starttime`, `endtime`. One composite index `(action, log_status, protocol, version)` serves combined searches of the low-cardinality columns. Single-column indexes on `version` (6 values), `protocol` (11), `action` and `log_status` (2) were deliberately **not** created: they match 10–50 % of the table, where an index does not beat a scan (a full scan measures ~2.4–3.9 ms at 100k rows) but would slow imports. Query plans (`manage.py benchmark_search --plans`) confirm the chosen indexes are used; multi-field queries use the most selective index and filter the few remaining rows.

Remaining limitations: `COUNT(*)` for very broad filters is O(matching rows); with millions of rows that, and the low-cardinality scans, would be the first things to revisit (PostgreSQL, or covering indexes). Import time grows with the number of indexes.

## Timing definition and benchmark

`search_time_ms` / `search_time_seconds` are measured with `time.perf_counter()` around exactly the database work: the `COUNT(*)` query plus the single page query (including fetching its rows into Python). It **excludes** request parsing/validation, JSON serialisation, HTTP and network, and the browser.

Measured with `python manage.py benchmark_search --runs 50` on the real data (100,000 events, Windows 11 laptop, Python 3.11, SQLite 3.42, warm cache, first page of 50 rows, each query using values from a real stored row):

| Query | Matches | Median ms |
|---|---:|---:|
| serialno / account-id / instance-id / srcaddr / dstaddr / dstport / bytes / starttime / endtime (single field) | 1–3 | 0.83 – 0.92 |
| srcport | 110 | 1.14 |
| packets | 9,026 | 1.45 |
| protocol | 9,074 | 1.62 |
| version | 16,780 | 2.40 |
| action | 49,868 | 3.59 |
| log-status | 50,119 | 3.92 |
| srcaddr + dstport | 1 | 0.98 |
| account-id + protocol + action + log-status | 1 | 0.99 |
| action + log-status + protocol + version | 411 | 1.35 |
| action + bytes | 1 | 0.92 |
| all 15 fields | 1 | 1.41 |

Import of the full archive: ~17 s (HTTP upload through the dev server, after enlarging SQLite's page cache; 37 s before that change). Figures are from one machine and will differ elsewhere. They were not measured inside Docker.

## Environment variables

See `.env.example`. Backend settings (`backend/config/settings.py`): `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATA_DIR`, `MAX_UPLOAD_BYTES`, `MAX_EXTRACTED_BYTES`, `MAX_ARCHIVE_MEMBERS`, `INGEST_BATCH_SIZE`, `LOG_LEVEL`. The nginx upload cap (`client_max_body_size`, 200m) must be raised together with `MAX_UPLOAD_BYTES`.

## Troubleshooting

- **`DJANGO_SECRET_KEY` error on startup:** set it in `.env` (Docker) or export `DJANGO_DEBUG=true` for local development.
- **"Cannot reach the server" in the UI:** check `docker compose ps` / `docker compose logs backend`; in development make sure `runserver` is on port 8000.
- **413 from nginx on upload:** archive exceeds 200 MB; raise both limits.
- **`database is locked` / 503 during an import:** SQLite allows one writer; searches keep working (WAL) but a second upload waits up to 30 s.
- **Start over:** `docker compose down -v` removes the data volume.

## Known limitations and verification status

- Import is synchronous inside the upload request (the UI shows an "importing" state). If the import fails it is rolled back and can be retried with the same file.
- Only the first occurrence of a `serialno` is kept; conflicting records with a reused serial in a later archive are skipped as duplicates.
- No authentication (assignment scope).
- **Verification status:** the backend tests, frontend tests, lint, type-check, production build and real-archive import/search (through HTTP and the UI dev server) were executed by the author. The Docker Compose setup was built and started with Docker Desktop on Windows, and the application was confirmed working in the browser at <http://localhost:8080>. Benchmarks were measured outside Docker only; the author did not separately record Docker import or search timings.
