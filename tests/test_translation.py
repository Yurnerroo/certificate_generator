"""Unit tests for the UA -> EN translation post-processing helpers.

These only exercise the pure, offline `_fix_capitalization` step -- not the
actual network-dependent Google/MyMemory backends -- so they run fast and
without internet access, per the reported "alicante" -> "Alicante" bug.
"""
from __future__ import annotations

import pytest

from app.services.translation import _fix_capitalization


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("alicante, spain", "Alicante, Spain"),
        ("ivano-frankivsk city, ukraine", "Ivano-Frankivsk City, Ukraine"),
        ("Kyiv", "Kyiv"),
        ("customer service standard", "Customer Service Standard"),
        ("already Correct, Text", "Already Correct, Text"),
        ("", ""),
        ("(kyiv)", "(Kyiv)"),
    ],
)
def test_fix_capitalization(raw: str, expected: str):
    assert _fix_capitalization(raw) == expected
