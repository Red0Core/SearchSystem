"""Utility helpers for normalization, transliteration and query classification."""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple, TypedDict
from urllib.parse import parse_qs, urlparse

from .brands import normalize_brand_token, resolve_brand_canonical

CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")
URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
ARTICLE_CHAR_PATTERN = re.compile(r"^[0-9A-Za-z\-_/\\)]+$")

STOPWORDS = {
    "the",
    "a",
    "an",
    "и",
    "в",
    "на",
    "для",
    "с",
    "без",
    "под",
    "из",
    "до",
    "по",
    "от",
    "to",
    "for",
    "with",
    "без",
    "масло",
    "фильтр",
    "к",
    "как",
    "and",
}


class QueryKind(str, Enum):
    URL = "url"
    ARTICLE = "article"
    BRAND_ONLY = "brand_only"
    BRAND_WITH_GENERIC = "brand_with_generic"
    GENERIC_ONLY = "generic_only"
    UNKNOWN = "unknown"


class QueryClassification(TypedDict, total=False):
    kind: QueryKind
    query: str
    tokens: List[str]
    brands: List[str]
    brand_originals: Dict[str, str]
    generic_tokens: List[str]
    normalized_code: str
    url_tokens: List[str]


BRAND_SYNONYMS: Dict[str, str] = {
    # fallback mappings if manufacturer.txt is not available
    "kamaz": "kamaz",
    "камаз": "kamaz",
    "toyota": "toyota",
    "тойота": "toyota",
    "gazpromneft": "gazpromneft",
    "газпромнефть": "gazpromneft",
    "samsung": "samsung",
    "самсунг": "samsung",
}

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


def normalize_manufacturer(name: Optional[str]) -> str:
    if not name:
        return ""
    base = normalize_brand_token(name)
    canonical = resolve_brand_canonical(base)
    if canonical:
        return canonical
    if base in BRAND_SYNONYMS:
        return BRAND_SYNONYMS[base]
    return base


def is_probable_article_query(q: str) -> bool:
    cleaned = q.strip()
    if not cleaned:
        return False
    if " " in cleaned and len(cleaned) > 20:
        return False
    digit_like = sum(1 for ch in cleaned if ch.isdigit() or ch in "-_/\\")
    return digit_like / max(len(cleaned), 1) > 0.5


def extract_url_tokens(q: str) -> List[str]:
    if not q or not URL_PATTERN.search(q):
        return []
    parsed = urlparse(q)
    tokens: List[str] = []
    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts:
        tokens.append(_strip_non_alnum(path_parts[-1]))
    for values in parse_qs(parsed.query).values():
        for value in values:
            tokens.append(_strip_non_alnum(value))
    return [token for token in tokens if token]


def _strip_non_alnum(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value)


def transliterate_query(q: str) -> str:
    if not q:
        return ""
    if CYRILLIC_PATTERN.search(q):
        return "".join(RU_TO_LATIN.get(ch.lower(), ch) for ch in q)
    # naive latin->ru by chunk matching
    result = []
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


def _resolve_brand_from_token(token: str) -> Tuple[Optional[str], str]:
    normalized = normalize_brand_token(token)
    canonical = resolve_brand_canonical(normalized)
    if canonical:
        return canonical, normalized
    transliterated = transliterate_query(token)
    normalized_tr = normalize_brand_token(transliterated)
    canonical_tr = resolve_brand_canonical(normalized_tr)
    if canonical_tr:
        return canonical_tr, normalized_tr
    return None, normalized


def _tokenize_query(q: str) -> List[str]:
    return [token for token in re.split(r"[\s,;|]+", q) if token]


def detect_brand_tokens(tokens: Sequence[str]) -> Tuple[List[str], Dict[str, str]]:
    """Return canonical brand keys plus their original token representation."""
    found: List[str] = []
    originals: Dict[str, str] = {}
    for token in tokens:
        canonical, _ = _resolve_brand_from_token(token)
        if canonical and canonical not in originals:
            originals[canonical] = token
            found.append(canonical)
    return found, originals


def _collect_generic_tokens(tokens: Sequence[str], brand_originals: Dict[str, str]) -> List[str]:
    generic: List[str] = []
    brand_tokens = set(brand_originals.values())
    for token in tokens:
        norm = normalize_brand_token(token)
        if not norm:
            continue
        if token in brand_tokens:
            continue
        if norm.isdigit() and len(norm) > 3:
            # numbers likely part codes -> treat as generic context
            generic.append(token)
            continue
        if norm in STOPWORDS:
            continue
        generic.append(token)
    return generic


def classify_query(q: str) -> QueryClassification:
    stripped = (q or "").strip()
    info: QueryClassification = {"kind": QueryKind.UNKNOWN, "query": stripped}
    if not stripped:
        return info
    if URL_PATTERN.search(stripped):
        tokens = extract_url_tokens(stripped)
        info.update({"kind": QueryKind.URL, "url_tokens": tokens})
        return info
    if is_probable_article_query(stripped) and ARTICLE_CHAR_PATTERN.match(stripped):
        info.update({"kind": QueryKind.ARTICLE, "normalized_code": normalize_code(stripped)})
        return info

    tokens = _tokenize_query(stripped)
    info["tokens"] = tokens
    if not tokens:
        return info

    brand_keys, originals = detect_brand_tokens(tokens)
    generic_tokens = _collect_generic_tokens(tokens, originals)
    info["brands"] = brand_keys
    info["brand_originals"] = originals
    info["generic_tokens"] = generic_tokens

    if brand_keys:
        if generic_tokens:
            info["kind"] = QueryKind.BRAND_WITH_GENERIC
        else:
            info["kind"] = QueryKind.BRAND_ONLY
    elif generic_tokens:
        info["kind"] = QueryKind.GENERIC_ONLY
    else:
        info["kind"] = QueryKind.UNKNOWN
    return info


def hash_query(q: str) -> str:
    return hashlib.sha256(q.encode("utf-8")).hexdigest()
