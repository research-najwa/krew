"""Saudi Arabia public holidays — updated annually.

Eid dates are based on astronomical predictions and may shift by +/- 1 day
based on official moon sighting announcements from the Saudi Supreme Court.
Last updated: 2026-03-18
"""
from datetime import date

# Fixed holidays (same Gregorian date every year)
FOUNDING_DAY = (2, 22)  # February 22
NATIONAL_DAY = (9, 23)  # September 23

# Eid dates by year (must be updated annually before each Eid season)
_EID_DATES: dict[int, dict[str, list[date]]] = {
    2025: {
        "eid_fitr": [date(2025, 3, 30), date(2025, 3, 31), date(2025, 4, 1)],
        "eid_adha": [date(2025, 6, 6), date(2025, 6, 7), date(2025, 6, 8), date(2025, 6, 9), date(2025, 6, 10)],
    },
    2026: {
        "eid_fitr": [date(2026, 3, 20), date(2026, 3, 21), date(2026, 3, 22), date(2026, 3, 23)],
        "eid_adha": [date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29), date(2026, 5, 30)],
    },
    2027: {
        "eid_fitr": [date(2027, 3, 9), date(2027, 3, 10), date(2027, 3, 11), date(2027, 3, 12)],
        "eid_adha": [date(2027, 5, 16), date(2027, 5, 17), date(2027, 5, 18), date(2027, 5, 19), date(2027, 5, 20)],
    },
}


def get_saudi_holidays(year: int) -> list[date]:
    """Return all Saudi public holidays for a given year.

    For Eid dates, these are pre-configured per year based on
    astronomical predictions. Update _EID_DATES when official dates
    are announced.
    """
    holidays = [
        date(year, *FOUNDING_DAY),  # Founding Day
        date(year, *NATIONAL_DAY),  # National Day
    ]

    year_eids = _EID_DATES.get(year, {})
    holidays.extend(year_eids.get("eid_fitr", []))
    holidays.extend(year_eids.get("eid_adha", []))

    return sorted(holidays)


def get_holiday_name(d: date) -> str | None:
    """Return the name of the holiday (bilingual) if the date is a holiday, else None."""
    holidays = get_saudi_holidays(d.year)
    if d not in holidays:
        return None

    if d.month == FOUNDING_DAY[0] and d.day == FOUNDING_DAY[1]:
        return "Founding Day / يوم التأسيس"
    if d.month == NATIONAL_DAY[0] and d.day == NATIONAL_DAY[1]:
        return "National Day / اليوم الوطني"

    year_eids = _EID_DATES.get(d.year, {})
    if d in year_eids.get("eid_fitr", []):
        return "Eid Al-Fitr / عيد الفطر"
    if d in year_eids.get("eid_adha", []):
        return "Eid Al-Adha / عيد الأضحى"

    return "Public Holiday / إجازة رسمية"


def format_holidays_for_prompt(year: int) -> str:
    """Format holidays as a string for inclusion in agent system prompts."""
    holidays = get_saudi_holidays(year)
    lines = []
    for h in holidays:
        name = get_holiday_name(h)
        lines.append(f"  - {h.isoformat()} ({h.strftime('%A')}): {name}")
    return "\n".join(lines)
