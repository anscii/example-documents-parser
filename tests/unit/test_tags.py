import pytest

from app.ingestion.normalizers.tags import normalize_tags


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (None, [], False),
        ([], [], False),
        (["energy", "water"], ["energy", "water"], False),
        (["Energy", "ENERGY", "energy"], ["energy"], False),
        ([None], [], True),
        (["energy", None], ["energy"], True),
        ("water,energy", ["energy", "water"], False),
        ("energy; renewables", ["energy", "renewables"], False),
        ({"topic": "climate"}, ["climate"], False),
        (123, [], True),
        ("", [], False),
    ],
)
def test_normalize_tags(value, expected, expect_warning):
    result, warning = normalize_tags(value)
    assert result == expected
    assert (warning is not None) == expect_warning
