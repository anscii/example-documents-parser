_TRUE_STRINGS = {"yes", "true"}
_FALSE_STRINGS = {"no", "false"}


def coerce_nullable_bool(value: object) -> tuple[bool | None, str | None, str | None]:
    """Normalize a nullable boolean field (open_access, peer_reviewed).

    Returns (value, raw, warning). bool passes through; int 0/1 ->
    False/True; "yes"/"no"/"true"/"false" (case-insensitive) -> bool;
    anything else -> None + warning. raw = str(original), or None for null.
    """
    if value is None:
        return None, None, None

    raw = str(value)

    if isinstance(value, bool):
        return value, raw, None
    if isinstance(value, int):
        if value == 1:
            return True, raw, None
        if value == 0:
            return False, raw, None
        return None, raw, f"unexpected integer for boolean field: {value!r}"
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_STRINGS:
            return True, raw, None
        if text in _FALSE_STRINGS:
            return False, raw, None
        return None, raw, f"unrecognized boolean value: {value!r}"
    return (
        None,
        raw,
        f"unexpected type for boolean field: {type(value).__name__}: {value!r}",
    )
