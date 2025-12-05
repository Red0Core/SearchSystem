# Search System Architecture

This repository contains a lightweight FastAPI + Elasticsearch service for fuzzy
product lookup. The pipeline is intentionally small:

1. **Normalize input** — collapse repeated letters, strip punctuation, and apply
   a few static brand aliases.
2. **Transliterate** — convert normalized text to ASCII so Latin/Cyrillic input
   land in the same field.
3. **Phonetics** — build Double Metaphone keys from the normalized text and keep
   them in dedicated fields.
4. **Search** — run one Elasticsearch query with text, transliteration, and
   phonetic clauses plus fuzzy product-code matching.

## Components

- `app/phonetics.py` — normalization, transliteration, and phonetic helpers.
- `app/importer.py` — reads `offers.json`, adds transliterated/phonetic fields,
  and bulk-loads documents.
- `app/indexing.py` — creates the `products` index from `product-mapping.json`
  and injects synonym lists when available.
- `app/search.py` — builds and executes the unified Elasticsearch query.
- `app/main.py` — FastAPI wiring for `/health`, `/search`, and `/reindex`.

## Data shape

Documents carry a few search-oriented extras in addition to the source data:

| Field | Purpose |
| --- | --- |
| `titleTranslit` | Transliteration of `title` (normalized + ASCII) for Latin/Cyrillic parity. |
| `titlePhonetic` | Phonetic key derived from the normalized `title`. |
| `phonetic` | Phonetic key derived from `title + manufacturer`. |

All three are populated in `app/importer.py` via the helpers in
`app/phonetics.py`.

## Query flow

`search_products` runs a single bool query with parallel clauses:

1. Text `multi_match` over `title`, `titleTranslit`, and manufacturer fields
   with fuzziness.
2. Transliteration assists: an additional strict `multi_match` and a softer
   `match` against `titleTranslit` to handle token splits and typos.
3. Phonetic `multi_match` over `titlePhonetic`, `titleTranslit.phonetic`,
   `title.phonetic`, `manufacturer.phonetic`, and the precomputed `phonetic`
   field.
4. Fuzzy product-code clause and a tiny `match_all` to keep
   `minimum_should_match=1` satisfied.

Only one round-trip to Elasticsearch is performed; results echo the normalized
query, scores, and `_source` contents for API/CLI consumers.
