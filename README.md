# Books Monitor: Crawler + Scheduler + API (FastAPI + MongoDB)

This project crawls the demo site https://books.toscrape.com, detects changes daily, and serves data via a secure REST API.

## Features

- Async crawler with retries, pagination, and raw HTML snapshots.
- MongoDB storage (Motor) with indexes for efficient queries and deduplication.
- Change detection using content hashing and change logs.
- Daily scheduler (APScheduler) and change report generation (JSON).
- FastAPI server with API key auth, rate limiting, pagination, filtering and sorting.
- Config via `.env` (Pydantic Settings), structured logging, and tests.

## Tech Stack

- Python 3.10+
- FastAPI, Uvicorn
- Motor (MongoDB async driver)
- httpx (async HTTP)
- BeautifulSoup + lxml (HTML parsing)
- APScheduler (daily jobs)
- Pydantic v2 + pydantic-settings

## Quick Start

1. Create and activate a virtual environment

```
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```
pip install -r requirements.txt
```

3. Copy environment and edit if needed

```
cp .env.example .env
```

4. Start MongoDB (Docker Compose)

```
docker compose up -d mongo
```

5. Initialize and run the API

```
uvicorn app.api.main:app --reload --port 8000
```

## Configuration (.env)

Copy `.env.example` to `.env` and adjust as needed:

```
# Mongo
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=books_monitor

# Crawl behavior
BASE_URL=https://books.toscrape.com
CONCURRENCY=12
REQUEST_TIMEOUT=20
MAX_RETRIES=3
USER_AGENT="BooksMonitorBot/1.0 (+https://example.com/bot)"

# API security & limits
API_KEYS=dev-key-1
RATE_LIMIT_PER_HOUR=100

# Scheduler
RUN_SCHEDULER_IN_API=true
SCHEDULER_CRON="0 2 * * *"           # use daily cron OR set interval below
SCHEDULER_INTERVAL_SECONDS=
SCHEDULER_RUN_ON_START=true           # run first job immediately on startup

# Logging & reports
LOG_LEVEL=INFO
LOGS_DIR=logs
REPORT_DIR=reports
```

Notes:
- On API startup, we ensure MongoDB indexes and backfill `category_norm` (lower-case of `category`) for existing documents to stabilize filtering and hashing.
- The scheduler can run embedded in the API (default) or as a separate process via `python -m app.scheduler.main`.

## API

- Swagger UI: http://localhost:8000/docs
- Authentication: Header `X-API-Key: <your key>` (configure in `.env` via `API_KEYS`)
- Rate limit: default 100 req/hour per API key (in-memory; can be extended)

### Endpoints

- GET `/books`
  - Query params:
    - `category`: case-insensitive. Internally matches `category_norm` (lower-case) and also legacy `category` case-insensitively.
    - `min_price`, `max_price`
    - `rating` (0–5)
    - `sort_by` in {`rating`, `price`, `reviews`} and `order` in {`asc`, `desc`}
    - `page`, `page_size`
  - Response: `PaginatedBooks { total, page, page_size, items[] }` where items are `BookPublic` (no `raw_html`, no `content_hash`).
- GET `/books/{book_id}` where `book_id` = UPC
  - Query param: `include_raw=true` to include `raw_html` and `content_hash` in the JSON response (used for debugging/diffing).
- GET `/changes`
  - Query params: `since` (ISO 8601), `type` in {`new`, `update`}, `limit`, `offset`
  - Tip: if you add a timezone offset (e.g., `+00:00`), URL-encode the plus sign as `%2B`. The server also tolerates accidental spaces instead of `+`.

## Folder Structure

```
app/
  api/
    main.py
    deps.py
    routers/
      books.py
      changes.py
  config/
    settings.py
    logging.py
  crawler/
    crawler.py
    parser.py
    runner.py
  db/
    mongo.py
    indexes.py
  models/
    book.py
    change.py
  scheduler/
    main.py
    report.py
  utils/
    http_client.py
    hashing.py
    rate_limiter.py
    auth.py
    time.py
tests/
```

## MongoDB Documents

### `books` Collection (sample)

```
{
  "_id": ObjectId(...),
  "upc": "a1b2c3d4",
  "name": "A Light in the Attic",
  "description": "...",
  "category": "Poetry",
  "category_norm": "poetry",
  "price_excl_tax": 51.77,
  "price_incl_tax": 51.77,
  "availability": 22,
  "num_reviews": 0,
  "image_url": "https://.../media/cache/xx.jpg",
  "rating": 3,
  "source_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
  "content_hash": "sha256:...",
  "raw_html": "<html>...</html>",
  "first_seen": "2025-09-30T00:00:00+00:00",
  "last_seen": "2025-09-30T00:00:00+00:00"
}
```

### `changes` Collection (sample)

```
{
  "_id": ObjectId(...),
  "book_upc": "a1b2c3d4",
  "change_type": "update",  // or "new"
  "changes": [
    {"field": "price_excl_tax", "old": 49.99, "new": 51.77}
  ],
  "timestamp": "2025-09-30T00:00:00+00:00"
}
```

## Testing

Run unit tests offline (no real Mongo or network calls). We use an in-memory fake Motor DB and disable the scheduler during tests.

```
pytest -q
```

With coverage:

```
pytest -q --cov=app --cov=tests --cov-report=term-missing
```

## Security Notes

- Keep API keys secret in `env`.
