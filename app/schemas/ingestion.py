from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IngestionRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    source_file: str
    file_hash: str


class IngestionRunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_file: str
    file_hash: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    total_lines: int | None
    raw_loaded_count: int | None
    skipped_count: int | None
    error_message: str | None


class IngestionErrorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_number: int
    error_category: str
    error_detail: str | None


class IngestionRunDetail(IngestionRunListItem):
    normalize_pending: int
    dedup_pending: int
    scoring_pending: int
    error_count: int
    sample_errors: list[IngestionErrorSummary]
