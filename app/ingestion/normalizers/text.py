import re

WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: object) -> tuple[str | None, str | None]:
    """Normalize a free-text field (title, abstract, body, region).

    Returns (value, warning).
    """
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"expected string, got {type(value).__name__}: {value!r}"

    stripped = value.strip()
    if not stripped:
        return None, None
    return stripped, None


def normalize_title_for_grouping(title: str) -> str:
    """Lowercase, strip, and collapse internal whitespace for duplicate-detection grouping."""
    return WHITESPACE_RE.sub(" ", title.strip()).lower()
