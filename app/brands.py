"""Helpers for loading and resolving manufacturer brand metadata."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, TypedDict

from rapidfuzz import fuzz, process

from .config import settings
from .data_files import ensure_data_file

logger = logging.getLogger(__name__)


class BrandIndex(TypedDict):
    canonical_by_variant: Dict[str, str]
    synonyms_by_canonical: Dict[str, Set[str]]


_brand_index: Optional[BrandIndex] = None
_canonical_brands: List[str] = []
MANUFACTURER_FILE = Path("manufacturer.txt")

SPECIAL_BRAND_OVERRIDES = {
    "комз": "kamaz",
    "комаз": "kamaz",
    "кемаз": "kamaz",
    "кама3": "kamaz",
    "камазз": "kamaz",
    "кэмз": "kamaz",
    "тайота": "toyota",
    "таёта": "toyota",
    "тойёта": "toyota",
    "тойета": "toyota",
    "мерсес": "mercedes",
    "лукойл": "lukoil",
    "лукоил": "lukoil",
}

CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
GENERIC_MANUFACTURER_TOKENS = {
    "запчасти",
    "детали",
    "деталь",
    "гидропривод",
    "motor",
    "corporation",
    "corp",
    "company",
    "co",
    "inc",
    "ltd",
    "group",
    "группа",
    "компания",
    "ооо",
    "zao",
    "зао",
    "ooo",
    "llc",
    "holding",
    "завод",
    "производство",
    "производитель",
    "комплекс",
}


def normalize_brand_token(value: Optional[str]) -> str:
    """Normalize brand-like tokens to lowercase alphanumeric strings."""
    if not value:
        return ""
    return re.sub(r"[^0-9a-zа-яё]+", "", value.lower())


def load_manufacturers(path: str | Path = MANUFACTURER_FILE) -> List[str]:
    file_path = ensure_data_file(path, settings.manufacturers_source_url or None)
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
    seen: Set[str] = set()
    ordered: List[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _select_canonical(tokens: Sequence[str]) -> str:
    for token in tokens:
        if token not in GENERIC_MANUFACTURER_TOKENS:
            return token
    return tokens[0]


def build_brand_index(manufacturer_lines: List[str]) -> BrandIndex:
    canonical_by_variant: Dict[str, str] = {}
    synonyms_by_canonical: Dict[str, Set[str]] = {}

    for line in manufacturer_lines:
        tokens = _extract_tokens(line)
        if not tokens:
            continue

        canonical = _select_canonical(tokens)
        reused = _existing_canonical_for_token(canonical, canonical_by_variant)
        if reused:
            canonical = reused

        synonyms = synonyms_by_canonical.setdefault(canonical, set())
        _register_variant(canonical, canonical, canonical_by_variant, synonyms)

        for token in tokens:
            _register_variant(canonical, token, canonical_by_variant, synonyms)

        full_line_variant = normalize_brand_token(line)
        _register_variant(canonical, full_line_variant, canonical_by_variant, synonyms)

    return {
        "canonical_by_variant": canonical_by_variant,
        "synonyms_by_canonical": synonyms_by_canonical,
    }


def _existing_canonical_for_token(token: str, canonical_by_variant: Dict[str, str]) -> Optional[str]:
    for variant in _variant_forms(token):
        if variant in canonical_by_variant:
            return canonical_by_variant[variant]
    return None


def _register_variant(
    canonical: str,
    token: str,
    canonical_by_variant: Dict[str, str],
    synonyms: Set[str],
) -> None:
    for variant in _variant_forms(token):
        if not variant:
            continue
        if variant not in canonical_by_variant:
            canonical_by_variant[variant] = canonical
        synonyms.add(variant)


def _variant_forms(token: str) -> Set[str]:
    variants: Set[str] = set()
    normalized = normalize_brand_token(token)
    if normalized:
        variants.add(normalized)
    mirror = _mirror_token(token)
    if mirror:
        variants.add(mirror)
    if normalized:
        mirror_of_norm = _mirror_token(normalized)
        if mirror_of_norm:
            variants.add(mirror_of_norm)
    return variants


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
LATIN_TO_RU.update(
    {
        "oi": "ой",
    }
)


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
    global _canonical_brands
    if _brand_index is not None:
        return _brand_index
    lines = load_manufacturers(path)
    _brand_index = build_brand_index(lines)
    _canonical_brands = sorted(_brand_index["synonyms_by_canonical"].keys())
    logger.info(
        "Initialized brand index with %s canonical entries", len(_brand_index["synonyms_by_canonical"])
    )
    return _brand_index


def get_brand_index() -> BrandIndex:
    return _brand_index or {"canonical_by_variant": {}, "synonyms_by_canonical": {}}


def get_all_canonical_brands() -> List[str]:
    if _canonical_brands:
        return _canonical_brands
    index = get_brand_index()
    return sorted(index["synonyms_by_canonical"].keys())


def is_known_brand_key(key: str) -> bool:
    return key in get_brand_index().get("synonyms_by_canonical", {})


def resolve_brand_canonical(value: str) -> Optional[str]:
    if not value:
        return None
    index = get_brand_index()
    return index["canonical_by_variant"].get(value)


def get_synonyms_for_brand(canonical: str) -> Set[str]:
    index = get_brand_index()
    return index["synonyms_by_canonical"].get(canonical, set())


def find_brand_for_token(token: str, *, score_threshold: int = 65) -> Optional[str]:
    """Resolve a token to a canonical brand using exact or fuzzy matching."""
    if not token:
        return None

    for variant in _variant_forms(token) or {normalize_brand_token(token)}:
        if not variant:
            continue
        override = SPECIAL_BRAND_OVERRIDES.get(variant)
        if override:
            logger.debug(
                "brand_fuzzy override: token=%r → brand=%s",
                token,
                override,
            )
            return override
        canonical = resolve_brand_canonical(variant)
        if canonical:
            return canonical

    normalized = normalize_brand_token(token)
    if not normalized:
        return None

    choices = get_all_canonical_brands()
    if not choices:
        return None
    match = process.extractOne(
        normalized,
        choices,
        scorer=fuzz.WRatio,
        score_cutoff=score_threshold,
    )
    if not match:
        return None
    best_brand, score, _ = match
    if not _passes_brand_family_guard(normalized, best_brand):
        return None
    logger.debug(
        "brand_fuzzy: token=%r → brand=%s score=%s",
        token,
        best_brand,
        score,
    )
    return best_brand


def _passes_brand_family_guard(source: str, candidate: str) -> bool:
    if not source or not candidate:
        return False
    if not _first_letter_guard(source, candidate):
        return False
    return _length_guard(source, candidate)


def _first_letter_guard(source: str, candidate: str) -> bool:
    source_letters = _first_letter_variants(source)
    candidate_letters = _first_letter_variants(candidate)
    return bool(source_letters & candidate_letters)


def _first_letter_variants(value: str) -> Set[str]:
    letters: Set[str] = set()
    if value:
        letters.add(value[0])
    mirror = _mirror_token(value)
    if mirror:
        letters.add(mirror[0])
    return letters


def _length_guard(source: str, candidate: str) -> bool:
    diff = abs(len(source) - len(candidate))
    max_len = max(len(source), len(candidate))
    if max_len <= 3:
        return diff == 0
    if max_len <= 6:
        return diff <= 2
    return diff <= 3
