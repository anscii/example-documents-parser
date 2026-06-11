import pytest

from app.ingestion.record_validator import InvalidRecord, ValidRecord, classify


@pytest.mark.parametrize(
    ("line", "expected_type", "expected_data", "expected_category"),
    [
        ('{"a": 1}', ValidRecord, {"a": 1}, None),
        ("", InvalidRecord, None, "invalid_json"),
        ("{}", InvalidRecord, None, "empty"),
        ("[]", InvalidRecord, None, "not_object"),
        ('"just a string"', InvalidRecord, None, "not_object"),
        ("123", InvalidRecord, None, "not_object"),
        ('{"broken": true}', InvalidRecord, None, "broken_stub"),
        ('{"title": "Broken JSON"', InvalidRecord, None, "invalid_json"),
        ("not json at all", InvalidRecord, None, "invalid_json"),
    ],
)
def test_classify(line, expected_type, expected_data, expected_category):
    result = classify(line)

    assert isinstance(result, expected_type)
    if isinstance(result, ValidRecord):
        assert result.data == expected_data
    else:
        assert result.category == expected_category
        assert result.detail
