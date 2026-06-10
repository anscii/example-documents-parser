from __future__ import annotations

from pydantic import BaseModel


class DuplicateGroupSummary(BaseModel):
    group_id: int
    size: int
    canonical_document_id: int
    normalized_title: str


class DuplicateStats(BaseModel):
    total_groups: int
    total_duplicates: int
    avg_group_size: float
    top_groups: list[DuplicateGroupSummary]


class QualityScoreDistribution(BaseModel):
    min: float | None
    max: float | None
    mean: float | None
    median: float | None
    p25: float | None
    p75: float | None
    histogram: list[int]


class StatsResponse(BaseModel):
    total_documents: int
    by_status: dict[str, int]
    by_document_type: dict[str, int]
    by_region: dict[str, int]
    by_language: dict[str, int]
    top_tags: dict[str, int]
    duplicate_stats: DuplicateStats
    quality_score_distribution: QualityScoreDistribution
