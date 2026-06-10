import pytest

from app.ingestion.normalizers.numbers import coerce_float, coerce_int, normalize_version


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (None, None, False),
        (5, 5, False),
        (5.7, 5, False),
        ("5", 5, False),
        ("5.0", 5, False),
        ("many", None, True),
        (True, None, True),
        ([], None, True),
    ],
)
def test_coerce_int(value, expected, expect_warning):
    result, warning = coerce_int(value)
    assert result == expected
    assert (warning is not None) == expect_warning


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (None, None, False),
        (0.85, 0.85, False),
        (1, 1.0, False),
        ("0.5", 0.5, False),
        ("high", None, True),
        (True, None, True),
        ([], None, True),
    ],
)
def test_coerce_float(value, expected, expect_warning):
    result, warning = coerce_float(value)
    assert result == expected
    assert (warning is not None) == expect_warning


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (None, None, False),
        ("1.0", "1.0", False),
        ("draft", "draft", False),
        ("", None, False),
        (1, "1", False),
        (1.5, "1.5", False),
        (True, None, True),
    ],
)
def test_normalize_version(value, expected, expect_warning):
    result, warning = normalize_version(value)
    assert result == expected
    assert (warning is not None) == expect_warning
