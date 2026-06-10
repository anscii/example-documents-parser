CANONICAL_STATUSES = {"draft", "published", "archived", "unknown"}
_INT_STATUS_MAP = {0: "draft", 1: "published", 2: "archived"}


def normalize_status(value: object) -> tuple[str, str, str | None]:
    """Normalize the `status` field. Returns (value, raw, warning).

    Canonical values are {draft, published, archived, unknown}. str matches the
    4 canonical names case-insensitively (else "unknown" + warning); bool
    True/False -> published/draft; int 0/1/2 -> draft/published/archived,
    other ints -> "unknown"; null -> "unknown". raw = repr(original).
    """
    raw = repr(value)

    if value is None:
        return "unknown", raw, None
    if isinstance(value, bool):
        return ("published" if value else "draft"), raw, None
    if isinstance(value, int):
        return _INT_STATUS_MAP.get(value, "unknown"), raw, None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in CANONICAL_STATUSES:
            return text, raw, None
        return "unknown", raw, f"unrecognized status: {value!r}"
    return "unknown", raw, f"unexpected type for status: {type(value).__name__}: {value!r}"
