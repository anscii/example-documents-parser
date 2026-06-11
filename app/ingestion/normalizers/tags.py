def normalize_tags(value: object) -> tuple[list[str], str | None]:
    """Normalize the `tags` field. Returns (value, warning).

    list -> [str], filtering out null/non-string elements first (e.g. [null] -> [],
    ["energy", null] -> ["energy"]) with a warning whenever an element was dropped.
    CSV/semicolon-separated string -> split. dict -> values filtered to [str], same
    drop-and-warn behavior as the list case. int/other -> [] + warning. null -> [].
    Result is deduped, lowercased, and sorted.
    """
    if value is None:
        return [], None

    warning: str | None = None

    if isinstance(value, list):
        tokens = [item for item in value if isinstance(item, str)]
        if len(tokens) != len(value):
            warning = "tags list contained non-string elements, which were dropped"
    elif isinstance(value, str):
        separator = ";" if ";" in value else ","
        tokens = value.split(separator)
    elif isinstance(value, dict):
        tokens = [v for v in value.values() if isinstance(v, str)]
        if len(tokens) != len(value):
            warning = "tags dict contained non-string values, which were dropped"
    else:
        return [], f"unexpected type for tags: {type(value).__name__}: {value!r}"

    cleaned = sorted({token.strip().lower() for token in tokens if token.strip()})
    return cleaned, warning
