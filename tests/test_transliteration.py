"""Unit tests for the deterministic UA -> Latin transliteration service."""
from __future__ import annotations

import pytest

from app.services.transliteration import transliterate, transliterate_name


@pytest.mark.parametrize(
    "uk,expected",
    [
        ("Марук Надія", "Maruk Nadiia"),
        ("Зданевич Юрій", "Zdanevych Yurii"),
        ("Євген", "Yevhen"),
        ("Їжак", "Yizhak"),
        ("Йосип", "Yosyp"),
        ("Ілля", "Illia"),
        ("Оля Мар'яна", "Olia Mariana"),
        ("ЩИРЕНКО", "SHCHYRENKO"),
    ],
)
def test_known_transliterations(uk: str, expected: str):
    assert transliterate(uk) == expected


def test_word_initial_vs_mid_word_forms():
    # "є" at word start -> "ye"; mid-word -> "ie"
    assert transliterate("Євген") == "Yevhen"
    assert transliterate("Гаєвич") == "Haievych"


def test_hyphenated_name_each_part_gets_word_initial_rules():
    assert transliterate("Анна-Марія") == "Anna-Mariia"


def test_empty_and_whitespace_only():
    assert transliterate("") == ""
    assert transliterate_name("   ") == ""


def test_preserves_non_cyrillic_and_digits():
    assert transliterate("Group 2026") == "Group 2026"


def test_transliterate_name_trims_whitespace():
    assert transliterate_name("  Марук Надія  ") == "Maruk Nadiia"
