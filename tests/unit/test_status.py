import pytest

from app.ingestion.normalizers.status import normalize_status


@pytest.mark.parametrize(
    ("value", "expected_value", "expect_warning"),
    [
        (None, "unknown", False),
        ("PUBLISHED", "published", False),
        ("Draft", "draft", False),
        ("archived", "archived", False),
        ("unknown", "unknown", False),
        ("", "unknown", True),
        (True, "published", False),
        (False, "draft", False),
        (0, "draft", False),
        (1, "published", False),
        (2, "archived", False),
        (3, "unknown", False),
        (4, "unknown", False),
        (5, "unknown", False),
        ("garbage", "unknown", True),
    ],
)
def test_normalize_status(value, expected_value, expect_warning):
    result, raw, warning = normalize_status(value)
    assert result == expected_value
    assert raw == repr(value)
    assert (warning is not None) == expect_warning
