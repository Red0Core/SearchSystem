# Search scoring & execution guide

The service issues one Elasticsearch query per request. Before it does, the
query string goes through three lightweight steps:

1. `normalize_query` — lowercase, collapse repeated letters, strip punctuation,
   and apply brand aliases.
2. `transliterate_text` — turn the normalized string into ASCII so Latin and
   Cyrillic share the same transliteration field.
3. `to_phonetic` — generate Double Metaphone codes from the normalized string.

## Query shape

The `_build_query` helper assembles a bool query with these clauses:

| Purpose | Payload | Boost |
| --- | --- | --- |
| Main text | `multi_match` over `title`, `title.russian`, `title.english`, `title.autocomplete`, `titleTranslit`, `titleTranslit.autocomplete`, `manufacturer`, `manufacturer.autocomplete` with `fuzziness=AUTO`, `operator=and`, `type=most_fields` | `2.0` |
| Transliteration (strict) | `multi_match` over `titleTranslit` + autocomplete subfield with `fuzziness=AUTO`, `operator=and` | `1.6` |
| Transliteration (looser split) | `match` on `titleTranslit` with `minimum_should_match=66%` and `fuzziness=AUTO` | `1.1` |
| Phonetics | `multi_match` over `title.phonetic`, `titleTranslit.phonetic`, `titlePhonetic`, `manufacturer.phonetic`, and document-level `phonetic` | `1.5` |
| Product codes | `multi_match` over `productCode` and `productCode.numeric` with `fuzziness=AUTO` | `1.2` |
| Safety net | `match_all` | `0.01` |

`minimum_should_match` is set to 1, so any successful clause yields hits.

## Fields that feed scoring

- `title`, `manufacturer` — raw text, with bilingual analyzers and brand
  synonyms.
- `titleTranslit` — normalized + transliterated `title` for cross-alphabet
  matching (with its own `.phonetic` subfield).
- `titlePhonetic` — Double Metaphone of the normalized `title`.
- `phonetic` — Double Metaphone of `title + manufacturer`.
- `productCode` (+ `.numeric`) — raw and n-grammed article search.

## RU summary

1. Нормализуем строку (нижний регистр, схлопывание букв, простые синонимы).
2. Транслитерируем, чтобы латиница и кириллица сходились в `titleTranslit`.
3. Считаем фонетические ключи и кладём их в отдельные поля.
4. Запускаем один `bool`-запрос в Elasticsearch: текстовая часть, пара
   поддержек по транслитерации, фонетический `multi_match`, артикулы и
   защитный `match_all`.
