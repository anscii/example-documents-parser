import pytest

from app.ingestion.normalizers.identity import (
    normalize_external_id,
    normalize_person_or_org_name,
    normalize_source_name,
)


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (None, None, False),
        ("", None, False),
        ("duplicate-id", None, False),
        ("DUPLICATE-ID", None, False),
        (12345, "12345", False),
        ("ext-123", "ext-123", False),
        ("  ext-123  ", "ext-123", False),
        (True, None, True),
    ],
)
def test_normalize_external_id(value, expected, expect_warning):
    result, warning = normalize_external_id(value)
    assert result == expected
    assert (warning is not None) == expect_warning


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (None, None, False),
        ("", None, False),
        ("   ", None, False),
        ("N/A", None, False),
        ("n/a", None, False),
        ("Unknown Author", None, False),
        ("unknown author", None, False),
        (42, "42", False),
        ("Jane Doe", "Jane Doe", False),
        ("  Jane Doe  ", "Jane Doe", False),
        (True, None, True),
    ],
)
def test_normalize_person_or_org_name(value, expected, expect_warning):
    result, warning = normalize_person_or_org_name(value)
    assert result == expected
    assert (warning is not None) == expect_warning


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (None, None, False),
        ("", None, False),
        ("unknown", None, False),
        ("Unknown", None, False),
        ("UNKNOWN", None, False),
        ("Feed A", "Feed A", False),
        (123, "123", False),
        ("  Bloomberg Green  ", "Bloomberg Green", False),
        (True, None, True),
    ],
)
def test_normalize_source_name(value, expected, expect_warning):
    result, warning = normalize_source_name(value)
    assert result == expected
    assert (warning is not None) == expect_warning
