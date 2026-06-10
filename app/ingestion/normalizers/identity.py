_DUPLICATE_ID_SENTINEL = "duplicate-id"
_JUNK_NAME_VALUES = {"n/a", "unknown author"}


def normalize_external_id(value: object) -> tuple[str | None, str | None]:
    """Normalize `external_id`. Returns (value, warning).

    `"duplicate-id"`, `""`, and null are all "no external id" sentinels -> None.
    Ints coerce to their string form.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"unexpected boolean for external_id: {value!r}"
    if isinstance(value, int):
        return str(value), None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == _DUPLICATE_ID_SENTINEL:
            return None, None
        return text, None
    return None, f"unexpected type for external_id: {type(value).__name__}: {value!r}"


def normalize_person_or_org_name(value: object) -> tuple[str | None, str | None]:
    """Normalize `author_name`/`organization_name`. Returns (value, warning).

    null/""/whitespace/"N/A"/"Unknown Author" -> None (caller maps None to the
    Unknown sentinel row). Ints coerce to their string form.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"unexpected boolean for name: {value!r}"
    if isinstance(value, int):
        return str(value), None
    if not isinstance(value, str):
        return None, f"unexpected type for name: {type(value).__name__}: {value!r}"

    text = value.strip()
    if not text or text.lower() in _JUNK_NAME_VALUES:
        return None, None
    return text, None


def normalize_source_name(value: object) -> tuple[str | None, str | None]:
    """Normalize `source_name`. Returns (value, warning).

    null/""/"unknown" (case-insensitive) -> None. Ints coerce to their string form.
    No `_raw` is retained; the original value is recoverable from raw_documents.raw_data.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"unexpected boolean for source_name: {value!r}"
    if isinstance(value, int):
        return str(value), None
    if not isinstance(value, str):
        return None, f"unexpected type for source_name: {type(value).__name__}: {value!r}"

    text = value.strip()
    if not text or text.lower() == "unknown":
        return None, None
    return text, None
