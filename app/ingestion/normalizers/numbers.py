import math


def coerce_int(value: object) -> tuple[int | None, str | None]:
    """Coerce a numeric field (citation_count, word_count, page_count) to int.

    Returns (value, warning). Numeric strings coerce; non-numeric strings
    (e.g. "many") -> None + warning.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"unexpected boolean for numeric field: {value!r}"
    if isinstance(value, int):
        return value, None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None, f"non-finite float for integer field: {value!r}"
        return int(value), None
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text), None
        except ValueError:
            try:
                parsed = float(text)
            except ValueError:
                return None, f"could not parse integer: {value!r}"
            if not math.isfinite(parsed):
                return None, f"non-finite float for integer field: {value!r}"
            return int(parsed), None
    return None, f"unexpected type for integer field: {type(value).__name__}: {value!r}"


def coerce_float(value: object) -> tuple[float | None, str | None]:
    """Coerce a numeric field (relevance_score) to float.

    Returns (value, warning). Numeric strings coerce; non-numeric strings
    (e.g. "high") -> None + warning.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"unexpected boolean for numeric field: {value!r}"
    if isinstance(value, (int, float)):
        parsed = float(value)
        if not math.isfinite(parsed):
            return None, f"non-finite float for float field: {value!r}"
        return parsed, None
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = float(text)
        except ValueError:
            return None, f"could not parse float: {value!r}"
        if not math.isfinite(parsed):
            return None, f"non-finite float for float field: {value!r}"
        return parsed, None
    return None, f"unexpected type for float field: {type(value).__name__}: {value!r}"


def normalize_version(value: object) -> tuple[str | None, str | None]:
    """Normalize the `version` field to a raw string, with no strict typing.

    Returns (value, warning).
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"unexpected boolean for version: {value!r}"
    if isinstance(value, str):
        text = value.strip()
        return (text or None), None
    if isinstance(value, (int, float)):
        return str(value), None
    return None, f"unexpected type for version: {type(value).__name__}: {value!r}"
