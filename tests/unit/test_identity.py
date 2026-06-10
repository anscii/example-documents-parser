import pytest

from app.ingestion.normalizers.identity import (
    normalize_external_id,
    normalize_person_or_org_name,
    normalize_source_name,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("duplicate-id", None),
        ("DUPLICATE-ID", None),
        (12345, "12345"),
        ("ext-123", "ext-123"),
        ("  ext-123  ", "ext-123"),
    ],
)
def test_normalize_external_id(value, expected):
    result, warning = normalize_external_id(value)
    assert result == expected
    assert warning is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("N/A", None),
        ("n/a", None),
        ("Unknown Author", None),
        ("unknown author", None),
        (42, "42"),
        ("Jane Doe", "Jane Doe"),
        ("  Jane Doe  ", "Jane Doe"),
    ],
)
def test_normalize_person_or_org_name(value, expected):
    result, warning = normalize_person_or_org_name(value)
    assert result == expected
    assert warning is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("unknown", None),
        ("Unknown", None),
        ("UNKNOWN", None),
        ("Feed A", "Feed A"),
        (123, "123"),
        ("  Bloomberg Green  ", "Bloomberg Green"),
    ],
)
def test_normalize_source_name(value, expected):
    result, warning = normalize_source_name(value)
    assert result == expected
    assert warning is None
