from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class ValidRecord:
    data: dict[str, Any]


@dataclass
class InvalidRecord:
    category: Literal["invalid_json", "not_object", "empty", "broken_stub"]
    detail: str


ClassifiedLine = ValidRecord | InvalidRecord


def classify(line: str) -> ClassifiedLine:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError as exc:
        return InvalidRecord(category="invalid_json", detail=str(exc))

    if not isinstance(parsed, dict):
        return InvalidRecord(
            category="not_object",
            detail=f"expected a JSON object, got {type(parsed).__name__}",
        )
    if not parsed:
        return InvalidRecord(
            category="empty",
            detail="expected a non-empty JSON object",
        )

    if parsed == {"broken": True}:
        return InvalidRecord(category="broken_stub", detail="broken stub record")

    return ValidRecord(data=parsed)
