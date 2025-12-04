"""Utility helpers for normalization and transliteration.

The original code also handled query classification and cache keys, but the
current service keeps the search surface small: static brand synonyms and
phonetics are enough. Only the pieces reused by ETL and transliteration remain
here.
"""
from __future__ import annotations

import re
from typing import Optional

CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")

# Simple transliteration map (Russian -> Latin). This is not exhaustive but
# covers common brand name characters.
RU_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}
LATIN_TO_RU = {v: k for k, v in RU_TO_LATIN.items() if v}


def normalize_code(code: Optional[str]) -> str:
    """Remove non-alphanumeric characters and uppercase the code."""
    if not code:
        return ""
    return re.sub(r"[^0-9A-Za-z]", "", code).upper()


def transliterate_query(q: str) -> str:
    """Switch between Cyrillic and Latin alphabets for fuzzy matching."""
    if not q:
        return ""
    if CYRILLIC_PATTERN.search(q):
        return "".join(RU_TO_LATIN.get(ch.lower(), ch) for ch in q)
    # naive latin->ru by chunk matching
    result: list[str] = []
    idx = 0
    lower_q = q.lower()
    while idx < len(lower_q):
        matched = False
        for latin, ru in sorted(LATIN_TO_RU.items(), key=lambda kv: -len(kv[0])):
            if lower_q.startswith(latin, idx):
                result.append(ru)
                idx += len(latin)
                matched = True
                break
        if not matched:
            result.append(lower_q[idx])
            idx += 1
    return "".join(result)
