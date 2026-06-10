CANONICAL_DOCUMENT_TYPES = {
    "report",
    "working_paper",
    "policy_brief",
    "journal_article",
    "news_article",
    "press_release",
    "dataset",
}


def normalize_document_type(value: object) -> tuple[str, str | None, str | None]:
    """Normalize the `document_type` field. Returns (value, raw, warning).

    Case-insensitive match against the 7 canonical types, else "unknown".
    raw = original value.
    """
    if value is None:
        return "unknown", None, None
    if not isinstance(value, str):
        return "unknown", str(value), f"unexpected type for document_type: {type(value).__name__}: {value!r}"

    raw = value
    text = value.strip().lower()
    if text in CANONICAL_DOCUMENT_TYPES:
        return text, raw, None
    return "unknown", raw, None
