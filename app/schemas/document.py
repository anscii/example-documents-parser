from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class AuthorRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class OrganizationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TagRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    author: AuthorRef
    organization: OrganizationRef
    source_name: str | None
    published_at: date | None
    language: str
    status: str
    document_type: str
    region: str | None
    tags: list[TagRef]
    citation_count: int | None
    relevance_score: float | None
    quality_score: float | None
    is_canonical: bool | None
    duplicate_group_id: int | None


class DuplicateGroupInfo(BaseModel):
    group_id: int
    group_size: int
    is_canonical: bool
    confidence: float | None


class DocumentDetail(DocumentSummary):
    raw_external_id: str | None
    abstract: str | None
    body: str | None
    published_at_raw: str | None
    updated_at: date | None
    updated_at_raw: str | None
    language_raw: str | None
    status_raw: str | None
    document_type_raw: str | None
    url: str | None
    url_valid: bool | None
    doi: str | None
    doi_valid: bool | None
    word_count: int | None
    page_count: int | None
    version: str | None
    open_access: bool | None
    peer_reviewed: bool | None
    normalization_warnings: list[str] | None
    created_at: datetime
    duplicate_group: DuplicateGroupInfo | None = None
