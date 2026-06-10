import re
from urllib.parse import urlparse

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_url(value: object) -> tuple[str | None, bool | None, str | None]:
    """Normalize the `url` field. Returns (value, valid, warning).

    The trimmed raw value is kept regardless of validity; `valid` reflects
    whether it parses as a URL with both a scheme and a network location.
    """
    if value is None:
        return None, None, None
    if not isinstance(value, str):
        return None, None, f"unexpected type for url: {type(value).__name__}: {value!r}"

    text = value.strip()
    if not text:
        return None, None, None

    parsed = urlparse(text)
    is_valid = bool(parsed.scheme and parsed.netloc)
    return text, is_valid, None


def normalize_doi(value: object) -> tuple[str | None, bool | None, str | None]:
    """Normalize the `doi` field. Returns (value, valid, warning).

    The trimmed raw value is kept regardless of validity; `valid` reflects
    whether it matches the DOI pattern `^10.\\d{4,9}/\\S+$`.
    """
    if value is None:
        return None, None, None
    if not isinstance(value, str):
        return None, None, f"unexpected type for doi: {type(value).__name__}: {value!r}"

    text = value.strip()
    if not text:
        return None, None, None

    is_valid = bool(DOI_PATTERN.match(text))
    return text, is_valid, None
