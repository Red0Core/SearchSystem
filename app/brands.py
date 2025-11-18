"""Brand parsing, normalization and detection helpers."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from .config import settings
from .data_files import ensure_data_file

logger = logging.getLogger(__name__)

MANUFACTURER_FILE = Path("manufacturer.txt")
TOKEN_PATTERN = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
ARTICLE_CODE_PATTERN = re.compile(
    r"^(?:[A-Z]{2}\d{3,}|\d{3,}[-/]\d+|[A-Z0-9-]{6,})$",
    re.IGNORECASE,
)
GENERIC_LABEL_TOKENS = {
    "group",
    "company",
    "co",
    "inc",
    "corp",
    "corporation",
    "motor",
    "motors",
    "automotive",
    "factory",
    "завод",
    "компания",
    "ооо",
    "zao",
    "зао",
    "ooo",
    "holding",
    "группа",
    "детали",
    "деталь",
    "запчасти",
    "parts",
}
NOISE_STARTERS = {
    "замок",
    "прокладка",
    "палец",
    "шланг",
    "втулка",
    "масла",
    "масел",
    "насос",
    "н/р",
    "для",
    "пружина",
    "поршень",
}
PRE_TRANSLIT_OVERRIDES = {
    "тойота": "toyota",
    "тайота": "toyota",
    "тоёта": "toyota",
    "таёта": "toyota",
    "тойёта": "toyota",
    "тойета": "toyota",
    "тойтоа": "toyota",
    "таиота": "toyota",
    "таета": "toyota",
    "лексус": "lexus",
    "лэксус": "lexus",
    "лехсус": "lexus",
    "лехус": "lexus",
    "лекс": "lexus",
    "лукойл": "lukoil",
    "лукоил": "lukoil",
    "лукоел": "lukoil",
}
POST_TRANSLIT_OVERRIDES = {
    "toiota": "toyota",
    "toeta": "toyota",
    "tayota": "toyota",
    "toyeta": "toyota",
    "toyata": "toyota",
    "toitoa": "toyota",
    "taiota": "toyota",
    "lexsus": "lexus",
    "leksus": "lexus",
    "lecsus": "lexus",
    "leksis": "lexus",
    "lukoil": "lukoil",
    "lukoyl": "lukoil",
}
MAJOR_BRAND_IDS = {"toyota", "lexus", "nissan", "infiniti", "honda", "acura", "lukoil"}
HARDCODED_BRANDS = {
    "toyota": {
        "Toyota",
        "TOYOTA",
        "ТОЙОТА",
        "Toyota Motor Corporation",
    },
    "lexus": {
        "LEXUS",
        "Lexus",
        "Лексус",
    },
    "lukoil": {
        "LUKOIL",
        "ЛУКОЙЛ",
        "Lukoil",
    },
}
QUERY_STOPWORDS = {
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
    "and",
    "как",
    "к",
    "фильтр",
}
RU_EQUIV_TRANSLATION = str.maketrans({"ё": "е", "й": "и"})

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
    "й": "i",
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


@dataclass
class Brand:
    id: str
    labels: set[str] = field(default_factory=set)
    tokens: set[str] = field(default_factory=set)


_brand_catalog: Dict[str, Brand] = {}
_brand_by_token: Dict[str, str] = {}


def normalize_brand_token(raw: str | None) -> str:
    """Normalize a brand token to lowercase latin characters."""
    if not raw:
        return ""
    text = raw.strip().lower()
    text = text.strip("-_.,")
    if not text:
        return ""
    override = PRE_TRANSLIT_OVERRIDES.get(text)
    if override:
        return override
    text = text.translate(RU_EQUIV_TRANSLATION)
    text = re.sub(r"[\"'`~!@#$%^&*+=\\[\\]{}:;,.?<>№]", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip("-_ ")
    if not text:
        return ""
    override = PRE_TRANSLIT_OVERRIDES.get(text)
    if override:
        return override
    transliterated = _transliterate_to_latin(text)
    token = re.sub(r"[^0-9a-z]+", "", transliterated)
    if not token:
        return ""
    token = POST_TRANSLIT_OVERRIDES.get(token, token)
    return token


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


def _transliterate_to_latin(text: str) -> str:
    return "".join(RU_TO_LATIN.get(ch, ch) for ch in text)


def _tokenize_text(text: str) -> List[str]:
    return TOKEN_PATTERN.findall(text or "")


def _looks_like_article_code(token: str) -> bool:
    if not token:
        return False
    if ARTICLE_CODE_PATTERN.match(token):
        return True
    letters = sum(1 for ch in token if ch.isalpha())
    digits = sum(1 for ch in token if ch.isdigit())
    return digits >= 3 and digits >= letters


def _is_noise_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return True
    tokens = _tokenize_text(stripped)
    if not tokens:
        return True
    first_token = tokens[0].lower()
    if _looks_like_article_code(tokens[0]):
        if len(tokens) > 1:
            return True
    if first_token in NOISE_STARTERS:
        return True
    # If digits dominate the string (article descriptions), treat as noise.
    digits = sum(1 for ch in stripped if ch.isdigit())
    letters = sum(1 for ch in stripped if ch.isalpha())
    return digits > 0 and digits >= letters * 2


def _split_segments(line: str) -> Iterable[str]:
    for segment in re.split(r"[,/|()]+", line):
        part = segment.strip()
        if not part:
            continue
        if _should_split_hyphen(part):
            for sub in re.split(r"-+", part):
                sub = sub.strip()
                if sub:
                    yield sub
        else:
            yield part


def _should_split_hyphen(value: str) -> bool:
    if "-" not in value:
        return False
    if value.isupper():
        return True
    normalized_parts = [normalize_brand_token(item) for item in value.split("-") if item]
    if len(normalized_parts) < 2:
        return False
    return all(part in MAJOR_BRAND_IDS for part in normalized_parts)


def _tokens_from_label(label: str) -> List[str]:
    tokens: List[str] = []
    for raw_token in _tokenize_text(label):
        normalized = normalize_brand_token(raw_token)
        if not normalized or len(normalized) < 3:
            continue
        if normalized in GENERIC_LABEL_TOKENS:
            continue
        tokens.append(normalized)
    return tokens


def _register_brand(label: str, brands: Dict[str, Brand], token_map: Dict[str, str]) -> None:
    tokens = _tokens_from_label(label)
    if not tokens:
        return
    canonical = tokens[0]
    brand = brands.setdefault(canonical, Brand(id=canonical))
    brand.labels.add(label.strip())
    for token in tokens:
        brand.tokens.add(token)
        token_map.setdefault(token, canonical)
    brand.tokens.add(canonical)
    token_map.setdefault(canonical, canonical)


def build_brand_catalog(lines: Sequence[str]) -> Tuple[Dict[str, Brand], Dict[str, str]]:
    brands: Dict[str, Brand] = {}
    token_map: Dict[str, str] = {}
    for line in lines:
        if _is_noise_line(line):
            continue
        for segment in _split_segments(line):
            _register_brand(segment, brands, token_map)
    for labels in HARDCODED_BRANDS.values():
        for label in labels:
            _register_brand(label, brands, token_map)
    return brands, token_map


def init_brands(path: str | Path = MANUFACTURER_FILE) -> Dict[str, Brand]:
    global _brand_catalog
    global _brand_by_token
    if _brand_catalog:
        return _brand_catalog
    lines = load_manufacturers(path)
    catalog, token_map = build_brand_catalog(lines)
    _brand_catalog = catalog
    _brand_by_token = token_map
    logger.info(
        "Initialized brand catalog with %s canonical brands and %s tokens",
        len(_brand_catalog),
        len(_brand_by_token),
    )
    return _brand_catalog


def get_brand_catalog() -> Dict[str, Brand]:
    if not _brand_catalog:
        init_brands()
    return _brand_catalog


def get_brand_token_map() -> Dict[str, str]:
    if not _brand_by_token:
        init_brands()
    return _brand_by_token


def extract_brand_ids_from_text(text: str, brand_map: Dict[str, str] | None = None) -> List[str]:
    brand_lookup = brand_map or get_brand_token_map()
    tokens = _tokenize_text(text or "")
    detected: List[str] = []
    seen = set()
    for token in tokens:
        normalized = normalize_brand_token(token)
        if not normalized:
            continue
        brand = brand_lookup.get(normalized)
        if brand and brand not in seen:
            seen.add(brand)
            detected.append(brand)
    return detected


def detect_brands_in_query(
    raw_query: str,
    brand_map: Dict[str, str] | None = None,
) -> Tuple[List[str], List[str], List[str]]:
    """Return detected brand ids, normalized non-brand tokens, and raw tokens."""

    brand_lookup = brand_map or get_brand_token_map()
    tokens = _tokenize_text(raw_query or "")
    brands: List[str] = []
    non_brand_terms: List[str] = []
    raw_non_brand_terms: List[str] = []
    seen = set()
    for token in tokens:
        normalized = normalize_brand_token(token)
        if not normalized:
            continue
        brand = brand_lookup.get(normalized)
        if brand:
            if brand not in seen:
                seen.add(brand)
                brands.append(brand)
            continue
        if len(normalized) < 2 or normalized in QUERY_STOPWORDS:
            continue
        non_brand_terms.append(normalized)
        raw_non_brand_terms.append(token)
    return brands, non_brand_terms, raw_non_brand_terms
