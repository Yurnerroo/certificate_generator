"""Unit tests for month/year date formatting (app/services/dates.py)."""
from __future__ import annotations

import pytest

from app.services import dates as dates_service


@pytest.mark.parametrize("month_idx", range(1, 13))
def test_format_dates_all_months(month_idx: int):
    uk, en = dates_service.format_dates(month_idx, 2026)
    assert uk == f"{dates_service.UA_MONTHS[month_idx - 1]}, 2026"
    assert en == f"{dates_service.EN_MONTHS[month_idx - 1]}, 2026"


def test_september_matches_reported_bug_case():
    uk, en = dates_service.format_dates(9, 2026)
    assert uk == "Вересень, 2026"
    assert en == "September, 2026"


@pytest.mark.parametrize("bad_month", [0, -1, 13, 100])
def test_format_dates_rejects_out_of_range_month(bad_month: int):
    with pytest.raises(ValueError):
        dates_service.format_dates(bad_month, 2026)


def test_month_choices_returns_12_ordered_entries():
    choices = dates_service.month_choices()
    assert len(choices) == 12
    assert [c["value"] for c in choices] == list(range(1, 13))
    assert choices[0]["label"] == "Січень"
    assert choices[11]["label"] == "Грудень"
