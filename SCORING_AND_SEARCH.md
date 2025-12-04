# Search scoring & execution guide

This note explains how `_score` is produced, how requests flow through the
service, and what keeps the <200 ms SLA attainable. English comes first, then a
Russian mirror.

## 1. Request journey (EN)

1. **Normalization** — `normalize_query` lowercases input, collapses repeated
   letters, strips punctuation, applies static brand synonyms, and harmonizes
   Latin digraphs (`sch`/`sh` → `ш`, `zh` → `ж`, `ch` → `ч`).
2. **Phonetics** — `to_phonetic` transliterates the normalized string to Latin
   and runs double metaphone so mixed-alphabet queries still align.
3. **Query building** — `_build_query` assembles a bool query with parallel
   `multi_match` clauses: text fields, optional phonetic fields, product codes,
   plus a tiny `match_all` to satisfy `minimum_should_match`.
4. **Execution** — Elasticsearch executes once; results are flattened to keep the
   original source fields and `_score` for FastAPI/CLI clients.

## 1. Путь запроса (RU)

1. **Нормализация** — `normalize_query` приводит строку к нижнему регистру,
   убирает повторяющиеся буквы, лишние символы, подменяет разговорные бренды и
   сводит латинские диграфы (`sch`/`sh` → `ш`, `zh` → `ж`, `ch` → `ч`).
2. **Фонетика** — `to_phonetic` транслитерирует нормализованную строку в
   латиницу и прогоняет через double metaphone, чтобы смешанные раскладки
   совпадали по звучанию.
3. **Сборка запроса** — `_build_query` ставит рядом `multi_match` по текстовым
   полям, опциональный фонетический `multi_match`, поиск по артикулам и
   крошечный `match_all` для `minimum_should_match`.
4. **Выполнение** — Elasticsearch вызывается один раз, результаты плоско
   сериализуются с исходными полями и `_score` для API/CLI.

## 2. Scoring ingredients (EN)

* **Text clause** — `multi_match` over `title^3`, `title.russian^2`,
  `title.english^2`, `title.autocomplete^1.5`, `manufacturer^2`,
  `manufacturer.autocomplete^1.5` with `fuzziness=AUTO`, boost `2.0`.
* **Phonetic clause** — optional `multi_match` over `title.phonetic^2`,
  `manufacturer.phonetic^2`, `phonetic` with boost `1.5`.
* **Code clause** — `multi_match` over `productCode^2`, `productCode.numeric`
  with `fuzziness=AUTO`, boost `1.2`.
* **Safety net** — `match_all` with `boost: 0.01` keeps results non-empty when
  everything else misses.

## 2. Что влияет на `_score` (RU)

* **Текстовая клауза** — `multi_match` по `title^3`, `title.russian^2`,
  `title.english^2`, `title.autocomplete^1.5`, `manufacturer^2`,
  `manufacturer.autocomplete^1.5` с `fuzziness=AUTO`, буст `2.0`.
* **Фонетическая клауза** — при наличии фонетики `multi_match` по
  `title.phonetic^2`, `manufacturer.phonetic^2`, `phonetic` с бустом `1.5`.
* **Артикулы** — `multi_match` по `productCode^2`, `productCode.numeric` с
  `fuzziness=AUTO`, буст `1.2`.
* **Подстраховка** — `match_all` с `boost: 0.01`, чтобы ответ не пустовал.

## 3. Latency guardrails

* **Normalization + phonetics** — pure CPU work, sub-millisecond.
* **Elasticsearch** — target <150 ms per request; only one round-trip is issued.
* **Post-processing** — flat dict construction for `_source` + `_score`, also
  sub-millisecond. No cache layer to invalidate or warm up.

## 3. Ограничения по времени

* **Нормализация и фонетика** — чистый CPU, менее миллисекунды.
* **Elasticsearch** — цель <150 мс за запрос; выполняется один вызов.
* **Постобработка** — упаковка `_source` и `_score` в плоские dict, тоже
  быстрее миллисекунды. Кэша нет — нечему устаревать.

## 4. Field & analyzer reference (EN)

| Field | Type | Purpose |
| --- | --- | --- |
| `manufacturer` | `text` + `phonetic` subfield | Brand names + phonetic matching |
| `title` | `text` + `phonetic` | Primary descriptive text |
| `search_text` | `text` | Concatenation of manufacturer/title/product code |
| `search_text_tr` | `text` | Transliteration of `search_text` for cross-alphabet matches |
| `product_code` / `productCode` | `text` | Raw article for display and fuzzy search |
| `product_code_normalized` | `keyword` | Analyzer-free article to support exact matches |
| `phonetic` | `text` | Precomputed phonetic key for the whole document |

Analyzers:

* `ru_en_search` — custom analyzer with Russian + English stop-words/stemmers,
  used by `manufacturer`, `title`, and `search_text`.
* `brand_phonetic_analyzer` — Elasticsearch phonetic plugin (Double Metaphone),
  exposed via `.phonetic` subfields to bridge латиница ↔ кириллица.
* `keyword` — no analysis; used for deterministic lookups.

## 4. Справочник полей и анализаторов (RU)

| Поле | Тип | Назначение |
| --- | --- | --- |
| `manufacturer` | `text` + `phonetic` | Названия брендов + фонетика |
| `title` | `text` + `phonetic` | Основное описание товара |
| `search_text` | `text` | Склейка manufacturer/title/product_code |
| `search_text_tr` | `text` | Транслитерированная версия `search_text` |
| `product_code` / `productCode` | `text` | Исходный артикул для отображения и фазы fuzziness |
| `product_code_normalized` | `keyword` | Очищенный артикул для точного поиска |
| `phonetic` | `text` | Предрасчитанная фонетика всего документа |

Анализаторы:

* `ru_en_search` — общий анализатор с русским/английским стеммингом.
* `brand_phonetic_analyzer` — Double Metaphone, используется в `.phonetic`.
* `keyword` — без анализа, идеально для `terms`/`filter`.

## 5. Example walkthrough (EN)

1. User searches for `"bosch sch"` with a typo/latin digraph.
2. `normalize_query` collapses it to `"бош"` thanks to the `sch` → `ш`
   override and brand synonyms.
3. `to_phonetic` transliterates to `"bosh"` and emits metaphone tokens.
4. `_build_query` runs text + phonetic + code clauses; Bosch listings match via
   both text fuzziness and the phonetic fields.

## 5. Пример шага за шагом (RU)

1. Пользователь вводит «bosch sch» с латинским диграфом.
2. `normalize_query` превращает его в «бош» (подстановка `sch` → `ш` плюс
   синонимы брендов).
3. `to_phonetic` транслитерирует в «bosh» и отдаёт metaphone-коды.
4. `_build_query` одновременно ищет по тексту, фонетике и артикулам; в выдаче
   оказываются позиции Bosch даже при смешанной раскладке.
