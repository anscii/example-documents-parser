from datetime import date

import pytest

from app.ingestion.normalizers.dates import normalize_date


@pytest.mark.parametrize(
    ("value", "expected_value", "expected_raw", "expect_warning"),
    [
        (None, None, None, False),
        ("", None, "", False),
        ("2020-05-01", date(2020, 5, 1), "2020-05-01", False),
        ("2020-05-01T12:00:00Z", date(2020, 5, 1), "2020-05-01T12:00:00Z", False),
        (20200501, date(2020, 5, 1), "20200501", False),
        ("invalid-date", None, "invalid-date", True),
        ("2023-13-45", None, "2023-13-45", True),
        (12345, None, "12345", True),
        (True, None, "True", True),
    ],
)
def test_normalize_date(value, expected_value, expected_raw, expect_warning):
    result, raw, warning = normalize_date(value)
    assert result == expected_value
    assert raw == expected_raw
    assert (warning is not None) == expect_warning
