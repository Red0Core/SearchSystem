# Product Search Service

FastAPI-based information-retrieval service that ranks spare-part offers with a
brand-first strategy. The stack is Elasticsearch 9.2.1 for search, optional
Redis for caching, and a Python (3.13+) application layer that performs brand
normalization, transliteration, and query re-ranking.

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

On startup, the app creates the `products` index, rebuilds the brand catalog
from `manufacturer.txt`, and (optionally) loads `offers.json` if the index is
empty.

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

## How the search pipeline works

The search stack is described in detail inside
[`ARCHITECTURE.md`](ARCHITECTURE.md) and
[`SCORING_AND_SEARCH.md`](SCORING_AND_SEARCH.md). The condensed version:

1. **Brand catalog** — `app/brands.py` parses `manufacturer.txt`, removes
   article-like noise, and produces canonical brand ids plus a lookup table that
   powers both ingestion (for `manufacturer_brand_tokens`) and queries.
2. **ETL** — `app/etl_loader.py` prepares each offer with search-friendly
   fields such as `search_text`, `search_text_tr`, normalized product codes, and
   brand token arrays.
3. **Classification** — every `/search` request is classified as URL,
   article, `brand_only`, `brand_with_generic`, or `generic_only`. Brand-aware
   paths keep both canonical ids and the raw generic tokens for Cyrillic search.
4. **Elasticsearch query** — brand-only paths filter strictly on
   `manufacturer_brand_tokens`; mixed queries first attempt the same filter and
   fall back to a boosted query if no hits are found; generic queries lean on
   fuzziness, phonetics, and transliteration fields.
5. **Latency guardrail** — cache hits return in <1 ms, while cold queries keep
   the <0.2 s SLA thanks to the small query bodies and aggressive logging of
   classification/build/ES timings.

Refer to the documentation files for diagrams, scoring formulas, and bilingual
descriptions of the entire pipeline.
