"""Utilities for text normalization and phonetic encoding.

The goal is to mimic the Java ``PhoneticUtil`` behavior using Python tools:
- normalize noisy input (lowercase, collapse repeated letters, drop punctuation)
- transliterate Cyrillic -> Latin for cross-script matching
- approximate Beider–Morse phonetics via the double metaphone algorithm

The output is used both for pre-indexing (``phonetic`` field) and query-time
matching when the user input is highly misspelled (e.g. "котерьпиллар").
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

from metaphone import doublemetaphone
from unidecode import unidecode

logger = logging.getLogger(__name__)

# Regex that keeps only letters/digits/spaces after transliteration.
_CLEAN_RE = re.compile(r"[^0-9a-zA-Zа-яА-ЯёЁ ]+")
# Collapse consecutive Cyrillic or Latin letters (e.g. "зоооп" -> "зоп").
_REPEATED_LETTER_RE = re.compile(r"([A-Za-zА-Яа-яЁё])\1+")


def normalize_text(text: str) -> str:
    """Normalize user input in the same spirit as the legacy Java code.

    Steps mirror the Java regex pipeline:
    - lowercase
    - collapse repeated letters
    - remove everything except letters/digits/spaces
    - collapse multiple spaces
    """

    lowered = (text or "").lower()
    collapsed = _REPEATED_LETTER_RE.sub(r"\1", lowered)
    cleaned = _CLEAN_RE.sub(" ", collapsed)
    compact = " ".join(cleaned.split())
    return compact


def _metaphone_tokens(tokens: Iterable[str]) -> list[str]:
    phonetics: list[str] = []
    for token in tokens:
        primary, secondary = doublemetaphone(token)
        for code in (primary, secondary):
            if code and code not in phonetics:
                phonetics.append(code)
    return phonetics


def to_phonetic(text: str) -> str:
    """Convert free-form text to a phonetic key.

    Transliteration + double metaphone is a decent approximation of the
    previous Beider–Morse setup while remaining lightweight and offline.
    Errors are swallowed and returned as an empty string to match Java's
    ``PhoneticUtil.toPhonetic`` behavior.
    """

    try:
        normalized = normalize_text(text)
        if not normalized:
            return ""
        transliterated = unidecode(normalized)
        tokens = transliterated.split()
        codes = _metaphone_tokens(tokens)
        return " ".join(codes)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.debug("phonetic conversion failed for %r: %s", text, exc)
        return ""
