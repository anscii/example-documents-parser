import pytest

from app.ingestion.normalizers.text import normalize_text, normalize_title_for_grouping


@pytest.mark.parametrize(
    ("value", "expected_value", "expect_warning"),
    [
        (None, None, False),
        ("", None, False),
        ("   ", None, False),
        ("  Climate Policy  ", "Climate Policy", False),
        ("Global", "Global", False),
        (123, None, True),
        ([], None, True),
    ],
)
def test_normalize_text(value, expected_value, expect_warning):
    result, warning = normalize_text(value)
    assert result == expected_value
    assert (warning is not None) == expect_warning


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Climate Policy in Southern Europe", "climate policy in southern europe"),
        ("climate policy in southern europe", "climate policy in southern europe"),
        ("URBAN DEVELOPMENT STRATEGIES", "urban development strategies"),
        ("Urban Development Strategies", "urban development strategies"),
        ("  Multiple   Spaces   Title  ", "multiple spaces title"),
    ],
)
def test_normalize_title_for_grouping(title, expected):
    assert normalize_title_for_grouping(title) == expected
