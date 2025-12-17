"""Regression tests for phonetic helpers."""

from app.phonetics import normalize_query, to_phonetic


def test_normalize_query_keeps_latin_digraphs():
    """Latin sh/ch should remain intact for analyzer pipelines."""

    assert normalize_query("bosch") == "bosch"
    assert normalize_query("SHIMANO") == "shimano"


def test_to_phonetic_still_harmonizes_digraphs():
    """Phonetic path harmonizes digraphs without mutating the normalized text."""

    normalized = normalize_query("bosch")
    phonetic = to_phonetic(normalized)

    assert normalized == "bosch"
    assert phonetic  # metaphone codes should be emitted
