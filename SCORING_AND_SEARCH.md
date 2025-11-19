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
