from datetime import date, datetime

from dateutil import parser as dateutil_parser


def normalize_date(value: object) -> tuple[date | None, str | None, str | None]:
    """Normalize a date field (published_at, updated_at).

    Handles ISO date/datetime strings, YYYYMMDD ints, empty/invalid strings, and null.
    Returns (value, raw, warning), where raw is the string form of the original
    value (for the `*_raw` columns), or None if the original value was null.
    """
    if value is None:
        return None, None, None

    raw = str(value)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, raw, None
        try:
            return date.fromisoformat(text), raw, None
        except ValueError:
            pass
        try:
            return dateutil_parser.parse(text).date(), raw, None
        except (ValueError, OverflowError):
            return None, raw, f"could not parse date: {value!r}"

    if isinstance(value, int) and not isinstance(value, bool):
        text = str(value)
        if len(text) == 8:
            try:
                return datetime.strptime(text, "%Y%m%d").date(), raw, None
            except ValueError:
                return None, raw, f"could not parse date: {value!r}"
        return None, raw, f"could not parse date: {value!r}"

    return None, raw, f"unexpected type for date: {type(value).__name__}: {value!r}"
