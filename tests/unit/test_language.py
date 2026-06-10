import pytest

from app.ingestion.normalizers.language import normalize_language


@pytest.mark.parametrize(
    ("value", "expected_value", "expected_raw", "expect_warning"),
    [
        (None, "unknown", None, False),
        ("en", "en", "en", False),
        ("EN", "en", "EN", False),
        ("english", "en", "english", False),
        ("English", "en", "English", False),
        ("sv", "sv", "sv", False),
        ("xx", "unknown", "xx", False),
        ("", "unknown", "", False),
        ("klingon", "unknown", "klingon", True),
        (123, "unknown", "123", True),
    ],
)
def test_normalize_language(value, expected_value, expected_raw, expect_warning):
    result, raw, warning = normalize_language(value)
    assert result == expected_value
    assert raw == expected_raw
    assert (warning is not None) == expect_warning
