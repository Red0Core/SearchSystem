"""Brand parsing, normalization and detection helpers."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from .config import settings
from .data_files import ensure_data_file

logger = logging.getLogger(__name__)

MANUFACTURER_FILE = Path("manufacturer.txt")
TOKEN_PATTERN = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
ARTICLE_CODE_PATTERN = re.compile(
    r"^(?:[A-Z]{2}\d{3,}|\d{3,}[-/]\d+|(?=.*\d)[A-Z0-9-]{6,})$",
    re.IGNORECASE,
)
GENERIC_LABEL_WORDS = {
    "group",
    "company",
    "co",
    "inc",
    "corp",
    "corporation",
    "limited",
    "ltd",
    "llc",
    "plc",
    "pte",
    "pty",
    "gmbh",
    "srl",
    "sro",
    "spa",
    "sa",
    "sas",
    "sasu",
    "ab",
    "ag",
    "oy",
    "oyj",
    "nv",
    "bv",
    "ptc",
    "holding",
    "holdings",
    "motor",
    "motors",
    "moto",
    "auto",
    "automobile",
    "automobiles",
    "automotive",
    "factory",
    "industries",
    "industry",
    "parts",
    "detail",
    "details",
    "service",
    "services",
    "equipment",
    "machines",
    "machinery",
    "construction",
    "products",
    "product",
    "systems",
    "system",
    "brand",
    "electronics",
    "electronic",
    "electric",
    "electrical",
    "oil",
    "lubricant",
    "lubricants",
    "fluid",
    "fluids",
    "liquid",
    "grease",
    "filter",
    "filters",
    "bearing",
    "bearings",
    "seal",
    "seals",
    "gasket",
    "gaskets",
    "ring",
    "rings",
    "belt",
    "belts",
    "hose",
    "hoses",
    "pipe",
    "pipes",
    "tube",
    "tubes",
    "pump",
    "pumps",
    "valve",
    "valves",
    "cylinder",
    "cylinders",
    "liner",
    "liners",
    "piston",
    "pistons",
    "bolt",
    "bolts",
    "nut",
    "nuts",
    "washer",
    "washers",
    "stud",
    "studs",
    "pin",
    "pins",
    "rod",
    "rods",
    "spring",
    "springs",
    "gear",
    "gears",
    "gidroprivod",
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
    "масло",
    "масла",
    "маслосъемный",
    "маслосъемная",
    "масл",
    "жидкость",
    "жидкости",
    "подшипник",
    "подшипники",
    "podshipnik",
    "kronshtein",
    "koromyslo",
    "gidro",
    "nasos",
    "колпачок",
    "колодка",
    "колодки",
    "прокладка",
    "прокладки",
    "втулка",
    "втулки",
    "болт",
    "болты",
    "гайка",
    "гайки",
    "шайба",
    "шайбы",
    "шланг",
    "шланги",
    "насос",
    "насосы",
    "трубка",
    "трубки",
    "кольцо",
    "кольца",
    "ремень",
    "ремни",
    "уплотнение",
    "уплотнения",
    "уплотнитель",
    "уплотнители",
    "уплотнительная",
    "уплотнительные",
    "уплотнительный",
    "фильтр",
    "фильтры",
    "сальник",
    "сальники",
    "клапан",
    "клапаны",
    "гидроцилиндр",
    "цилиндр",
    "цилиндры",
    "гидромотор",
    "поршень",
    "поршни",
    "шестерня",
    "шестерни",
    "корпус",
    "кронштейн",
    "рычаг",
    "рычаги",
    "пружина",
    "деталь",
    "детали",
    "запчасть",
    "кардан",
    "фара",
    "лампа",
    "лампы",
    "поддон",
    "насадка",
    "насадки",
    "крышка",
    "крышки",
    "кожух",
    "комплект",
    "комплекты",
    "опора",
    "опоры",
    "распылитель",
    "распылители",
    "шкворень",
    "сайлентблок",
    "сайлентблоки",
    "колесо",
    "колеса",
    "quanzhou",
    "shanghai",
    "moscow",
    "moskva",
    "saint",
    "petersburg",
    "china",
    "germany",
    "italy",
    "japan",
    "korea",
    "turkey",
    "russia",
}

GENERIC_SUFFIXES = [
    "ami",
    "yami",
    "kami",
    "yah",
    "akh",
    "ogo",
    "ego",
    "omu",
    "emu",
    "ami",
    "yakh",
    "akh",
    "ov",
    "ev",
    "iy",
    "yy",
    "iyu",
    "uyu",
    "aya",
    "oy",
    "ey",
    "iy",
    "im",
    "ym",
    "om",
    "em",
    "am",
    "yam",
    "iu",
    "ya",
    "ia",
    "a",
    "y",
    "i",
    "u",
    "e",
    "s",
    "es",
]
NOISE_STARTERS = {
    "замок",
    "прокладка",
    "прокладки",
    "палец",
    "пальц",
    "шланг",
    "шланги",
    "втулка",
    "втулки",
    "масло",
    "масла",
    "масел",
    "маслосъемный",
    "жидкость",
    "жидкости",
    "подшипник",
    "подшипники",
    "колпачок",
    "кольцо",
    "кольца",
    "насос",
    "насосы",
    "н/р",
    "для",
    "пружина",
    "пружины",
    "поршень",
    "поршни",
    "ремень",
    "ремни",
    "кронштейн",
    "крышка",
    "болт",
    "гайка",
    "шайба",
    "фильтр",
    "фильтры",
    "уплотнение",
    "уплотнения",
    "уплотнитель",
    "уплотнители",
    "опора",
    "опоры",
    "гидроцилиндр",
    "гидромотор",
    "деталь",
    "детали",
    "комплект",
    "комплекты",
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


def _transliterate_to_latin(text: str) -> str:
    return "".join(RU_TO_LATIN.get(ch, ch) for ch in text)


@dataclass
class Brand:
    id: str
    labels: set[str] = field(default_factory=set)
    tokens: set[str] = field(default_factory=set)


@dataclass
class LabelCandidate:
    text: str
    tokens: List[str]
    is_upper: bool
    has_latin: bool
    token_count: int
    hyphenated: bool


@dataclass
class TokenStats:
    occurrences: int = 0
    solo_occurrences: int = 0
    uppercase_occurrences: int = 0
    latin_occurrences: int = 0
    hyphen_occurrences: int = 0

    def score(self) -> float:
        return (
            self.solo_occurrences * 2
            + self.uppercase_occurrences
            + self.hyphen_occurrences
            + self.latin_occurrences * 0.5
        )


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


def _strip_generic_suffix(token: str) -> str:
    if not token:
        return ""
    base = token
    changed = True
    while changed:
        changed = False
        for suffix in GENERIC_SUFFIXES:
            if base.endswith(suffix) and len(base) - len(suffix) >= 4:
                base = base[: -len(suffix)]
                changed = True
                break
    return base


def _build_generic_label_tokens(words: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for word in words:
        normalized = normalize_brand_token(word)
        if not normalized:
            continue
        tokens.add(normalized)
        tokens.add(_strip_generic_suffix(normalized))
    return {token for token in tokens if token}


GENERIC_LABEL_TOKENS = _build_generic_label_tokens(GENERIC_LABEL_WORDS)
GENERIC_TOKEN_BASES = {
    token for token in (_strip_generic_suffix(item) for item in GENERIC_LABEL_TOKENS) if token
}


def _is_generic_like_token(token: str) -> bool:
    if not token:
        return True
    if token in GENERIC_LABEL_TOKENS:
        return True
    base = _strip_generic_suffix(token)
    if base in GENERIC_TOKEN_BASES:
        return True
    return False


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


def _tokenize_text(text: str) -> List[str]:
    return TOKEN_PATTERN.findall(text or "")


def _looks_all_caps(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return all(ch.isupper() for ch in letters)


def _contains_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text))


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
    parts = [segment.strip() for segment in value.split("-") if segment.strip()]
    if len(parts) < 2:
        return False
    normalized_parts = [normalize_brand_token(item) for item in parts]
    if len([p for p in normalized_parts if p]) < 2:
        return False
    # If both sides look like brand-ish tokens (letters and at least 3 chars), split.
    return all(part.isalpha() and len(part) >= 3 for part in normalized_parts if part)


def _tokens_from_label(label: str) -> List[str]:
    tokens: List[str] = []
    for raw_token in _tokenize_text(label):
        if _looks_like_article_code(raw_token):
            continue
        normalized = normalize_brand_token(raw_token)
        if not normalized or len(normalized) < 3:
            continue
        if _is_generic_like_token(normalized):
            continue
        tokens.append(normalized)
    return tokens


def _damerau_levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    len_a = len(a)
    len_b = len(b)
    dist = [[0] * (len_b + 1) for _ in range(len_a + 1)]
    for i in range(len_a + 1):
        dist[i][0] = i
    for j in range(len_b + 1):
        dist[0][j] = j
    for i in range(1, len_a + 1):
        for j in range(1, len_b + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dist[i][j] = min(
                dist[i - 1][j] + 1,
                dist[i][j - 1] + 1,
                dist[i - 1][j - 1] + cost,
            )
            if (
                i > 1
                and j > 1
                and a[i - 1] == b[j - 2]
                and a[i - 2] == b[j - 1]
            ):
                dist[i][j] = min(dist[i][j], dist[i - 2][j - 2] + cost)
    return dist[len_a][len_b]


def _fuzzy_brand_lookup(token: str, brand_lookup: Dict[str, str]) -> str | None:
    if len(token) < 4:
        return None
    best_brand: str | None = None
    best_score = 0.0
    for candidate, brand in brand_lookup.items():
        if candidate == token:
            return brand
        if len(candidate) < 4:
            continue
        if candidate[0] != token[0]:
            continue
        if abs(len(candidate) - len(token)) > 2:
            continue
        distance = _damerau_levenshtein(token, candidate)
        max_len = max(len(candidate), len(token))
        if distance > 3 or distance > max(1, max_len // 3):
            continue
        score = 1 - distance / max_len
        if score >= 0.6 and score > best_score:
            best_score = score
            best_brand = brand
    return best_brand


def _collect_candidates(lines: Sequence[str]) -> Tuple[List[LabelCandidate], Dict[str, TokenStats]]:
    candidates: List[LabelCandidate] = []
    stats: Dict[str, TokenStats] = defaultdict(TokenStats)
    for line in lines:
        if _is_noise_line(line):
            continue
        for segment in _split_segments(line):
            tokens = _tokens_from_label(segment)
            if not tokens:
                continue
            candidate = LabelCandidate(
                text=segment.strip(),
                tokens=tokens,
                is_upper=_looks_all_caps(segment),
                has_latin=_contains_latin(segment),
                token_count=len(tokens),
                hyphenated="-" in segment,
            )
            candidates.append(candidate)
            for token in tokens:
                stat = stats[token]
                stat.occurrences += 1
                if candidate.token_count == 1:
                    stat.solo_occurrences += 1
                if candidate.is_upper:
                    stat.uppercase_occurrences += 1
                if candidate.has_latin or _contains_latin(token):
                    stat.latin_occurrences += 1
                if candidate.hyphenated:
                    stat.hyphen_occurrences += 1
    return candidates, stats


def _select_trusted_tokens(stats: Dict[str, TokenStats]) -> set[str]:
    trusted: set[str] = set()
    for token, stat in stats.items():
        if not token:
            continue
        if _is_generic_like_token(token):
            continue
        if stat.solo_occurrences:
            trusted.add(token)
            continue
        if stat.occurrences <= 2 and (stat.uppercase_occurrences or stat.latin_occurrences):
            trusted.add(token)
            continue
        if stat.score() >= 2.5:
            trusted.add(token)
    return trusted


def _register_candidate(
    candidate: LabelCandidate,
    trusted_tokens: set[str],
    brands: Dict[str, Brand],
    token_map: Dict[str, str],
) -> None:
    canonical = next((token for token in candidate.tokens if token in trusted_tokens), None)
    if not canonical:
        return
    brand = brands.setdefault(canonical, Brand(id=canonical))
    brand.labels.add(candidate.text)
    for token in candidate.tokens:
        if token not in trusted_tokens:
            continue
        brand.tokens.add(token)
        token_map.setdefault(token, canonical)
    brand.tokens.add(canonical)
    token_map.setdefault(canonical, canonical)


def build_brand_catalog(lines: Sequence[str]) -> Tuple[Dict[str, Brand], Dict[str, str]]:
    candidates, stats = _collect_candidates(lines)
    trusted = _select_trusted_tokens(stats)
    brands: Dict[str, Brand] = {}
    token_map: Dict[str, str] = {}
    for candidate in candidates:
        _register_candidate(candidate, trusted, brands, token_map)
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


def get_normalized_brand_ids() -> List[str]:
    """Return a sorted list of canonical brand identifiers."""
    return sorted(get_brand_catalog().keys())


def extract_brand_ids_from_text(text: str, brand_map: Dict[str, str] | None = None) -> List[str]:
    brand_lookup = brand_map or get_brand_token_map()
    tokens = _tokenize_text(text or "")
    detected: List[str] = []
    seen = set()
    for token in tokens:
        normalized = normalize_brand_token(token)
        if not normalized:
            continue
        if _is_generic_like_token(normalized):
            continue
        brand = brand_lookup.get(normalized)
        if not brand:
            brand = _fuzzy_brand_lookup(normalized, brand_lookup)
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
        if _is_generic_like_token(normalized):
            non_brand_terms.append(normalized)
            raw_non_brand_terms.append(token)
            continue
        brand = brand_lookup.get(normalized)
        if not brand:
            brand = _fuzzy_brand_lookup(normalized, brand_lookup)
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
