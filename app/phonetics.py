"""Utilities for query normalization and phonetic encoding.

Two-step pipeline expected by the new search flow:

1) :func:`normalize_query` cleans the user text (lowercase, collapse repeated
   letters, strip punctuation) and applies a small Python-side synonym map so
   that aliases like ``"мерс"`` turn into ``"мерседес"`` *before* phonetics.
2) :func:`to_phonetic` accepts the normalized string, transliterates
   Cyrillic -> Latin, and generates a phonetic code (double metaphone) so that
   wildly misspelled queries such as ``"котерьпиллар"`` still align with
   canonical tokens like ``"caterpillar"``.

The resulting strings are fed to Elasticsearch in parallel: the normalized text
targets morphological analyzers, while the phonetic key hits phonetic fields.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

from metaphone import doublemetaphone
from unidecode import unidecode

logger = logging.getLogger(__name__)

# Regex that keeps only letters/digits/spaces during normalization.
_LETTER_DIGIT_SPACE_RE = re.compile(r"[^0-9a-zA-Zа-яА-ЯёЁ ]+")
# Collapse consecutive Cyrillic or Latin letters (e.g. "зоооп" -> "зоп").
_REPEATED_LETTER_RE = re.compile(r"([A-Za-zА-Яа-яЁё])\1+")
# After transliteration we keep only Latin letters/digits/spaces for metaphone.
_ASCII_ALNUM_SPACE_RE = re.compile(r"[^0-9a-zA-Z ]+")
# Phonetic harmonization rules to align common digraphs before transliteration.
_PHONETIC_REWRITE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sch"), "ш"),
    (re.compile(r"sh"), "ш"),
    (re.compile(r"zh"), "ж"),
    (re.compile(r"ch"), "ч"),
)

# Minimal brand synonym dictionary applied before phonetics. This mirrors the
# Java pipeline where aliases could be normalized on the Python side before
# hitting Elasticsearch analyzers.
BRAND_SYNONYMS: dict[str, str] = {
    "мерс": "мерседес",
    "мерседес": "мерседес",
    "беха": "bmw",
    "бмв": "bmw",
    "тойота": "toyota",
}


def normalize_query(text: str) -> str:
    """Normalize free-form input prior to search and phonetics.

    Mirrors the legacy Java ``SearchService`` normalization:

    1. Lowercase the input.
    2. Normalize common Latin digraphs to their Cyrillic phonemes so ``sch``
       and ``sh`` both become ``ш`` (and similar for ``zh``/``ch``), keeping
       phonetic output stable across alphabets.
    3. Collapse repeated letters using the ``(\p{L})\1+ -> $1`` style regex
       (e.g. ``"ооочень"`` → ``"очень"``).
    4. Strip everything except letters (Cyrillic+Latin), digits, and spaces.
    5. Collapse multiple spaces and trim.
    6. Apply a tiny Python-side synonym map so colloquial brand aliases map to
       canonical tokens (e.g. ``"мерс"`` → ``"мерседес"``, ``"беха"`` →
       ``"bmw"``) before phonetic generation.
    """

    lowered = (text or "").lower()
    harmonized = _apply_phonetic_overrides(lowered)
    collapsed = _REPEATED_LETTER_RE.sub(r"\1", harmonized)
    cleaned = _LETTER_DIGIT_SPACE_RE.sub(" ", collapsed)
    compact = " ".join(cleaned.split())
    logger.debug(
        "normalize_query raw=%r lowered=%r harmonized=%r collapsed=%r cleaned=%r compact=%r",
        text,
        lowered,
        harmonized,
        collapsed,
        cleaned,
        compact,
    )
    if not compact:
        logger.debug("normalize_query empty after cleaning")
        return ""

    tokens = [BRAND_SYNONYMS.get(token, token) for token in compact.split()]
    normalized = " ".join(tokens)
    logger.info(
        "normalize_query tokens=%s -> normalized=%r",
        tokens,
        normalized,
    )
    return normalized


def _apply_phonetic_overrides(value: str) -> str:
    """Unify common Latin digraphs with their Cyrillic phonetic counterparts.

    A lightweight static pass keeps phonetics stable regardless of whether the
    user typed "bosch", "bosh", or "бош": both ``sch`` and ``sh`` collapse to
    ``ш`` before transliteration, while ``zh``/``ch`` turn into ``ж``/``ч``.
    This helps :func:`to_phonetic` emit the same metaphone tokens for latin and
    Cyrillic spellings without adding runtime analyzers or extra ES filters.
    """

    adjusted = value
    for pattern, replacement in _PHONETIC_REWRITE_RULES:
        adjusted = pattern.sub(replacement, adjusted)
    return adjusted


def _metaphone_tokens(tokens: Iterable[str]) -> list[str]:
    phonetics: list[str] = []
    for token in tokens:
        primary, secondary = doublemetaphone(token)
        for code in (primary, secondary):
            if code and code not in phonetics:
                phonetics.append(code)
    return phonetics


def to_phonetic(normalized_text: str) -> str:
    """Generate a phonetic key from **already normalized** text.

    1. Transliterate Cyrillic → Latin using ``unidecode`` to keep tokens
       comparable across scripts.
    2. Retain only Latin letters/digits/spaces (phonetic encoders expect ASCII).
    3. Run double metaphone per token to approximate Beider–Morse behavior.

    Any error results in an empty string, mirroring the defensive Java helper.
    """

    try:
        if not normalized_text:
            logger.debug("to_phonetic skipped: empty normalized text")
            return ""
        transliterated = unidecode(normalized_text)
        ascii_only = _ASCII_ALNUM_SPACE_RE.sub(" ", transliterated)
        tokens = ascii_only.split()
        codes = _metaphone_tokens(tokens)
        phonetic = " ".join(codes)
        logger.info(
            "to_phonetic normalized=%r transliterated=%r ascii=%r tokens=%s codes=%s phonetic=%r",
            normalized_text,
            transliterated,
            ascii_only,
            tokens,
            codes,
            phonetic,
        )
        return phonetic
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.debug("phonetic conversion failed for %r: %s", normalized_text, exc)
        return ""
