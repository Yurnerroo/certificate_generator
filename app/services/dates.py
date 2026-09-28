"""Ukrainian month names and static UA -> EN month mapping.

Date handling is deliberately network-free: the certificate's date fields are
built purely from a month + year picked in the UI, so there's no dependency
on the (network-based) translation service for something this simple and
well-defined.
"""
from __future__ import annotations

# Ukrainian month names in the genitive-adjacent form used on the certificate
# (e.g. "Липень, 2026"), ordered 1-12 for the dropdown.
UA_MONTHS: list[str] = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
]

EN_MONTHS: list[str] = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_UA_TO_EN = dict(zip(UA_MONTHS, EN_MONTHS))


def month_choices() -> list[dict]:
    """Return [{"value": index_1_based, "label": "Липень"}, ...] for the UI."""
    return [{"value": i + 1, "label": name} for i, name in enumerate(UA_MONTHS)]


def format_dates(month: int, year: int) -> tuple[str, str]:
    """Given a 1-12 month index and a year, return (uk_date, en_date) strings.

    Example: format_dates(7, 2026) -> ("Липень, 2026", "July, 2026").
    """
    if not (1 <= month <= 12):
        raise ValueError(f"Month must be between 1 and 12, got {month}")
    ua_name = UA_MONTHS[month - 1]
    en_name = _UA_TO_EN[ua_name]
    return f"{ua_name}, {year}", f"{en_name}, {year}"
