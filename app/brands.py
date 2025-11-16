"""Helpers for loading and resolving manufacturer brand metadata."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, TypedDict

logger = logging.getLogger(__name__)


class BrandIndex(TypedDict):
    canonical_by_variant: Dict[str, str]
    synonyms_by_canonical: Dict[str, Set[str]]


_brand_index: Optional[BrandIndex] = None
MANUFACTURER_FILE = Path("manufacturer.txt")

CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")


def normalize_brand_token(value: Optional[str]) -> str:
    """Normalize brand-like tokens to lowercase alphanumeric strings."""
    if not value:
        return ""
    return re.sub(r"[^0-9a-zа-яё]+", "", value.lower())


def load_manufacturers(path: str | Path = MANUFACTURER_FILE) -> List[str]:
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Manufacturer dictionary file not found: %s", file_path)
        return []
    lines: List[str] = []
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
    return lines


def _extract_tokens(line: str) -> List[str]:
    tokens: List[str] = []
    for raw in re.split(r"[\s,;|/\\]+", line):
        normalized = normalize_brand_token(raw)
        if not normalized or normalized.isdigit():
            continue
        tokens.append(normalized)
    # keep order but drop duplicates
    seen: Set[str] = set()
    unique_tokens: List[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique_tokens.append(token)
    return unique_tokens


def build_brand_index(manufacturer_lines: List[str]) -> BrandIndex:
    canonical_by_variant: Dict[str, str] = {}
    synonyms_by_canonical: Dict[str, Set[str]] = {}
    for line in manufacturer_lines:
        tokens = _extract_tokens(line)
        if not tokens:
            continue
        canonical = tokens[0]
        synonyms = synonyms_by_canonical.setdefault(canonical, set())
        for token in tokens:
            canonical_by_variant.setdefault(token, canonical)
            synonyms.add(token)
            # Add transliterated mirror token to capture cross alphabet brands
            mirror = _mirror_token(token)
            if mirror and mirror not in synonyms:
                synonyms.add(mirror)
                canonical_by_variant.setdefault(mirror, canonical)
    return {
        "canonical_by_variant": canonical_by_variant,
        "synonyms_by_canonical": synonyms_by_canonical,
    }


def _mirror_token(token: str) -> str:
    if not token:
        return ""
    if CYRILLIC_PATTERN.search(token):
        return normalize_brand_token(_ru_to_latin(token))
    return normalize_brand_token(_latin_to_ru(token))


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


def _ru_to_latin(text: str) -> str:
    return "".join(RU_TO_LATIN.get(ch, ch) for ch in text.lower())


def _latin_to_ru(text: str) -> str:
    result: List[str] = []
    idx = 0
    lower = text.lower()
    while idx < len(lower):
        matched = False
        for latin, ru in sorted(LATIN_TO_RU.items(), key=lambda kv: -len(kv[0])):
            if lower.startswith(latin, idx):
                result.append(ru)
                idx += len(latin)
                matched = True
                break
        if not matched:
            result.append(lower[idx])
            idx += 1
    return "".join(result)


def init_brands(path: str | Path = MANUFACTURER_FILE) -> BrandIndex:
    global _brand_index
    if _brand_index is not None:
        return _brand_index
    lines = load_manufacturers(path)
    _brand_index = build_brand_index(lines)
    logger.info(
        "Initialized brand index with %s canonical entries", len(_brand_index["synonyms_by_canonical"])
    )
    return _brand_index


def get_brand_index() -> BrandIndex:
    return _brand_index or {"canonical_by_variant": {}, "synonyms_by_canonical": {}}


def resolve_brand_canonical(value: str) -> Optional[str]:
    if not value:
        return None
    index = get_brand_index()
    return index["canonical_by_variant"].get(value)


def get_synonyms_for_brand(canonical: str) -> Set[str]:
    index = get_brand_index()
    return index["synonyms_by_canonical"].get(canonical, set())
