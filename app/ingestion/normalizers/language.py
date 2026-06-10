ISO2_LANGUAGES = {"sv", "pt", "de", "en", "fr", "pl", "it", "nl", "es"}
FULL_NAME_TO_ISO2 = {"english": "en"}


def normalize_language(value: object) -> tuple[str, str | None, str | None]:
    """Normalize the `language` field. Returns (value, raw, warning).

    Recognized ISO-2 codes pass through; full names (e.g. "english") map to
    their ISO-2 code; "xx"/""/null and anything unrecognized -> "unknown".
    """
    if value is None:
        return "unknown", None, None
    if not isinstance(value, str):
        return "unknown", str(value), f"unexpected type for language: {type(value).__name__}: {value!r}"

    raw = value
    text = value.strip().lower()

    if not text or text == "xx":
        return "unknown", raw, None
    if text in ISO2_LANGUAGES:
        return text, raw, None
    if text in FULL_NAME_TO_ISO2:
        return FULL_NAME_TO_ISO2[text], raw, None
    return "unknown", raw, f"unrecognized language: {value!r}"
