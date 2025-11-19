# Search scoring & execution guide

This note explains how `_score` is produced, how requests flow through the
service, and how the <200 ms SLA is kept. Each section has an English description
followed by a Russian mirror.

## 1. Request journey (EN)

1. **Classification** — `classify_query` tokenizes the raw query, detects URLs,
   articles, canonical brand ids (via `detect_brands_in_query`), and non-brand
   tokens. Classification decides which execution path the query will take.
2. **Brand intent** — when brands are present we also capture `generic_tokens`
   (raw Cyrillic if available) so the ES query can stay in the same alphabet even
   if the normalized tokens are transliterated.
3. **Query building** — `build_es_query` creates a bool query with
   `track_total_hits=false` and uses helper functions to add `must`, `should`, and
   `filter` clauses. Highlights:
   * Brand-only → strict `filter` on `manufacturer_brand_tokens`, boosted
     `constant_score` clause for the same brands, plus a `multi_match` over
     manufacturer/title for intra-brand ranking.
   * Brand + generic → same filter plus a `multi_match` over the remaining terms.
     If the initial request returns fewer than `settings.brand_fallback_min_hits`
     documents, the service rebuilds the query without the filter but keeps a
     strong `should` boost on `manufacturer_brand_tokens` so branded documents
     still float to the top.
   * Generic-only → a `multi_match` across `title`, `search_text`, and
     `product_code` with `fuzziness=AUTO` and an optional phonetic `should`
     clause for transliteration mismatches.
   * Article / URL → dedicated branches: exact term match on
     `product_code_normalized` or a broad `multi_match` across `search_text` /
     `search_text_tr`.
4. **Execution & fallback** — the ES request is executed once. If the brand
   filter was active and produced fewer hits than the threshold, the service logs
   `brand_fallback` and immediately retries with the filter disabled (but still
   with boosted brands). Brand-only queries fall back when zero hits are found;
   brand+generic queries fall back when the number of hits is below the
   configured threshold.
5. **Serialization** — the response is trimmed to `id`, `manufacturer`,
   `product_code`, `title`, and `_score`. Timing metrics (classification,
   building, ES call, post-processing, total) are logged, surfaced in `/search`,
   and cached for 5 minutes.

## 1. Путь запроса (RU)

1. **Классификация** — `classify_query` разбирает запрос на URL/артикулы/бренды,
   вызывает `detect_brands_in_query` и решает ветку выполнения.
2. **Бренды** — помимо канонических id сохраняются «сырые» слова (например,
   «масло») в оригинальной раскладке; это позволяет `build_es_query` искать по
   кириллице, даже если нормализация перевела токены в латиницу.
3. **Сборка запроса** — `build_es_query` добавляет `must`/`should`/`filter`:
   * чистый бренд → фильтр `manufacturer_brand_tokens` + `constant_score` буст +
     `multi_match` по `manufacturer^4`, `title`, `search_text`;
   * бренд + описание → тот же фильтр, `multi_match` по generic-словам и сильный
     `should` для бренда; при нехватке документов выполняется fallback без
     фильтра, но с бустом бренда;
   * generic → `multi_match` по `title/search_text/product_code` +
     фонетический `should` по `manufacturer.phonetic`/`title.phonetic`;
   * артикулы / URL → отдельные ветки (точный `term` по
     `product_code_normalized` или `multi_match` по `search_text*`).
4. **Выполнение и fallback** — если активный бренд-фильтр не вернул нужное
   количество документов, в логах появится `brand_fallback`, после чего запрос
   повторится без фильтра. Для чистых брендов порог = 1, для смешанных —
   `settings.brand_fallback_min_hits`.
5. **Сериализация** — ответ содержит `id`, `manufacturer`, `product_code`,
   `title`, `_score`, а также тайминги. Результат кэшируется на 5 минут, так что
   повторные запросы укладываются в миллисекунды.

## 2. Scoring ingredients (EN)

* **Field boosts** — `title^3`, `product_code^4`, `manufacturer^2` (varies per
  clause) keep short titles and articles competitive.
* **Brand boosts** — constant-score should clause with boost 3–5 ensures any
  brand hit outranks non-brand matches when the filter is off.
* **Phonetic matches** — optional should clause over `.phonetic` subfields keeps
  transliterated queries aligned with Cyrillic documents.
* **Fuzziness** — all `multi_match` clauses use `AUTO` so minor typos (`тойтоа`)
  map to the intended brand/article strings.
* **Filters** — when applied, `manufacturer_brand_tokens` removes whole brands
  from consideration, forcing brand-first rankings.

## 2. Что влияет на `_score` (RU)

* **Boost поля** — `title^3`, `product_code^4`, `manufacturer^2` (в зависимости
  от клаузы) усиливают короткие заголовки и артикулы.
* **Брендовые бусты** — `constant_score` в `should` с коэффициентом 3–5 даёт
  ощутимое преимущество нужному бренду, даже если фильтр снят.
* **Фонетика** — дополнительный `should` по `manufacturer.phonetic` и
  `title.phonetic` помогает скрестить латиницу и кириллицу.
* **Fuzziness=AUTO** — ловит опечатки уровня «тойтоа», «leksus» и т. п.
* **Фильтры** — `terms` по `manufacturer_brand_tokens` полностью ограничивает
  выдачу нужными брендами, обеспечивая режим «brand first».

## 3. Latency guardrails

* **Classification** — purely CPU, <1 ms on average.
* **Query build** — string concatenations + dict assembly, ~0.1 ms.
* **Elasticsearch** — target <150 ms even with fallback (both requests happen
  back-to-back when needed).
* **Post-processing** — slicing `_source` and caching, <1 ms.
* **Cache hits** — bypass classification/ES entirely; total time ≈ serialization
  cost (<1 ms).

## 3. Ограничения по времени

* **Классификация** — <1 мс.
* **Сборка запроса** — ≈0.1 мс.
* **Elasticsearch** — цель <150 мс даже с повторным запросом.
* **Постобработка** — <1 мс.
* **Кэш** — попавший в кэш запрос укладывается в миллисекунду.

## 4. Field & analyzer reference (EN)

| Field | Type | Purpose |
| --- | --- | --- |
| `manufacturer` | `text` + `phonetic` subfield | Brand names + phonetic matching |
| `manufacturer_brand_tokens` | `keyword[]` | Canonical brand IDs for filters/boosts |
| `title` | `text` + `phonetic` | Primary descriptive text |
| `search_text` | `text` | Concatenation of manufacturer/title/product code |
| `search_text_tr` | `text` | Transliteration of `search_text` for cross-alphabet matches |
| `product_code` | `text` | Raw article for display |
| `product_code_normalized` | `keyword` | Analyzer-free article to support exact matches |

Analyzers:

* `ru_en_search` — custom analyzer with Russian + English stop-words/stemmers,
  used by `manufacturer`, `title`, and `search_text`.
* `brand_phonetic_analyzer` — Elasticsearch phonetic plugin (Double Metaphone),
  exposed via `.phonetic` subfields to bridge латиница ↔ кириллица.
* `keyword` — no analysis; used for filters and deterministic lookups.

## 4. Справочник полей и анализаторов (RU)

| Поле | Тип | Назначение |
| --- | --- | --- |
| `manufacturer` | `text` + `phonetic` | Названия брендов + фонетика |
| `manufacturer_brand_tokens` | `keyword[]` | Канонические id брендов для фильтра/бустов |
| `title` | `text` + `phonetic` | Основное описание товара |
| `search_text` | `text` | Склейка manufacturer/title/product_code |
| `search_text_tr` | `text` | Транслитерированная версия `search_text` |
| `product_code` | `text` | Исходный артикул для отображения |
| `product_code_normalized` | `keyword` | Очищенный артикул для точного поиска |

Анализаторы:

* `ru_en_search` — общий анализатор с русским/английским стеммингом.
* `brand_phonetic_analyzer` — Double Metaphone, используется в `.phonetic`.
* `keyword` — без анализа, идеально для `terms`/`filter`.

## 5. Example walkthrough (EN)

1. User types `"масло лукойл"`.
2. `classify_query` detects canonical brand `lukoil`, captures raw generic token
   `"масло"`, and emits `QueryKind.BRAND_WITH_GENERIC`.
3. `build_es_query` builds a bool query with:
   * `filter`: `manufacturer_brand_tokens` in `["lukoil"]`.
   * `must`: `multi_match` over `title^3`, `manufacturer`, `search_text` with
     `query="масло"`.
   * `should`: constant-score boost for `lukoil` (value 5).
4. ES executes the request. If no hits are returned, `search_products` reruns the
   query without the `filter`, but keeps the brand boost so Lukoil documents still
   outrank others.
5. Response: list of hits (id/manufacturer/title/product_code), `_score`,
   `brand_fallback=0/1`, timings, and the classification metadata for debugging.

## 5. Пример шага за шагом (RU)

1. Пользователь вводит «масло лукойл».
2. `classify_query` находит бренд `lukoil`, сохраняет исходное слово «масло» и
   выбирает `QueryKind.BRAND_WITH_GENERIC`.
3. `build_es_query` строит `bool`:
   * `filter`: `manufacturer_brand_tokens` содержит `lukoil`.
   * `must`: `multi_match` по `title^3`/`manufacturer`/`search_text` с запросом
     «масло».
   * `should`: `constant_score` c boost=5 для `lukoil`.
4. Если документов нет, `search_products` повторяет запрос без `filter`, но с тем
   же `should` — брендовые документы всё равно оказываются первыми.
5. Клиент получает результаты с `_score`, таймингами и пометкой `brand_fallback`.
