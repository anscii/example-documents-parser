import pytest

from app.ingestion.normalizers.links import normalize_doi, normalize_url


@pytest.mark.parametrize(
    ("value", "expected_value", "expected_valid", "expect_warning"),
    [
        (None, None, None, False),
        ("", None, None, False),
        (
            "https://example.com/report.pdf",
            "https://example.com/report.pdf",
            True,
            False,
        ),
        ("not-a-url", "not-a-url", False, False),
        ("http://", "http://", False, False),
        (123, None, None, True),
    ],
)
def test_normalize_url(value, expected_value, expected_valid, expect_warning):
    result, valid, warning = normalize_url(value)
    assert result == expected_value
    assert valid == expected_valid
    assert (warning is not None) == expect_warning


@pytest.mark.parametrize(
    ("value", "expected_value", "expected_valid", "expect_warning"),
    [
        (None, None, None, False),
        ("", None, None, False),
        ("10.1234/abcd", "10.1234/abcd", True, False),
        ("not-a-doi", "not-a-doi", False, False),
        (123, None, None, True),
    ],
)
def test_normalize_doi(value, expected_value, expected_valid, expect_warning):
    result, valid, warning = normalize_doi(value)
    assert result == expected_value
    assert valid == expected_valid
    assert (warning is not None) == expect_warning
