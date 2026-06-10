from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.tag import document_tags

if TYPE_CHECKING:
    from app.models.author import Author
    from app.models.organization import Organization
    from app.models.raw_document import RawDocument
    from app.models.tag import Tag


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "ix_documents_normalized_title_duplicate_group_id",
            "normalized_title",
            "duplicate_group_id",
        ),
        Index("ix_documents_status_document_type", "status", "document_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_document_id: Mapped[int] = mapped_column(
        ForeignKey("raw_documents.id", ondelete="CASCADE"), unique=True, index=True
    )
    raw_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_title: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    published_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    published_at_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)

    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))

    language: Mapped[str] = mapped_column(String(20))
    language_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    status_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_type: Mapped[str] = mapped_column(String(30), index=True)
    document_type_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doi_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    open_access: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    open_access_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    peer_reviewed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    peer_reviewed_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)

    duplicate_group_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_canonical: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duplicate_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    normalization_warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    author: Mapped["Author"] = relationship(back_populates="documents")
    organization: Mapped["Organization"] = relationship(back_populates="documents")
    tags: Mapped[list["Tag"]] = relationship(secondary=document_tags, back_populates="documents")
    raw_document: Mapped["RawDocument"] = relationship(back_populates="document")
