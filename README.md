# Product Search Service

A minimal FastAPI-based REST search service backed by Elasticsearch 9.2.1 and optional Redis caching.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) for dependency management
- Elasticsearch 9.2.1 running locally at `http://localhost:9200`
- Optional: Redis at `localhost:6379` (in-memory cache is used if Redis is not available)

## Setup

```bash
uv sync
```

### Data files

The service requires `offers.json` and `manufacturer.txt`. If those files are missing locally,
provide download locations via environment variables so the app can fetch them automatically:

```bash
export OFFERS_SOURCE_URL="https://example.com/offers.json"
export MANUFACTURERS_SOURCE_URL="https://example.com/manufacturer.txt"
```

When the environment variables are unset, the application expects both files to already be
present in the project root.

## Running the API

```bash
uv run uvicorn app.main:app --reload
```

On startup, the app creates the `products` index and (optionally) loads `offers.json` if it is empty.

### Health check

```
curl http://localhost:8000/health
```

### Search endpoint

```
curl --get 'http://localhost:8000/search' --data-urlencode 'q=тойота'
```

## CLI client

Interactive usage:

```bash
uv run python cli_search.py
```

Single query:

```bash
uv run python cli_search.py "toyota"
```

Batch execution using the provided queries file:

```bash
uv run python cli_search.py --batch queries_example.txt
```

## Reindexing data

To reload data from `offers.json`:

```bash
curl -X POST http://localhost:8000/reindex
```

> Note: The `/reindex` endpoint is served by FastAPI (default port `8000`).
> If you accidentally call Elasticsearch directly on port `9200` (e.g. `curl -X POST http://localhost:9200/reindex`),
> Elasticsearch returns HTTP 405 because it expects the `_reindex` API instead of our application route.
