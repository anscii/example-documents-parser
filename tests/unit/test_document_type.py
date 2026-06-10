import pytest

from app.ingestion.normalizers.document_type import normalize_document_type


@pytest.mark.parametrize(
    ("value", "expected_value", "expected_raw", "expect_warning"),
    [
        (None, "unknown", None, False),
        ("report", "report", "report", False),
        ("REPORT", "report", "REPORT", False),
        ("working_paper", "working_paper", "working_paper", False),
        ("policy_brief", "policy_brief", "policy_brief", False),
        ("journal_article", "journal_article", "journal_article", False),
        ("news_article", "news_article", "news_article", False),
        ("press_release", "press_release", "press_release", False),
        ("dataset", "dataset", "dataset", False),
        ("something_else", "unknown", "something_else", False),
        (123, "unknown", "123", True),
    ],
)
def test_normalize_document_type(value, expected_value, expected_raw, expect_warning):
    result, raw, warning = normalize_document_type(value)
    assert result == expected_value
    assert raw == expected_raw
    assert (warning is not None) == expect_warning
