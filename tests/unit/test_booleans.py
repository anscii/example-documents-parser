import pytest

from app.ingestion.normalizers.booleans import coerce_nullable_bool


@pytest.mark.parametrize(
    ("value", "expected_value", "expected_raw", "expect_warning"),
    [
        (None, None, None, False),
        (True, True, "True", False),
        (False, False, "False", False),
        (1, True, "1", False),
        (0, False, "0", False),
        (2, None, "2", True),
        ("yes", True, "yes", False),
        ("Yes", True, "Yes", False),
        ("no", False, "no", False),
        ("true", True, "true", False),
        ("FALSE", False, "FALSE", False),
        ("maybe", None, "maybe", True),
        (1.5, None, "1.5", True),
    ],
)
def test_coerce_nullable_bool(value, expected_value, expected_raw, expect_warning):
    result, raw, warning = coerce_nullable_bool(value)
    assert result == expected_value
    assert raw == expected_raw
    assert (warning is not None) == expect_warning
