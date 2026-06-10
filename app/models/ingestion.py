from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.raw_document import RawDocument


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    staged_path: Mapped[str] = mapped_column(String(1000))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="queued")
    total_lines: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_loaded_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skipped_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    errors: Mapped[list["IngestionError"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    raw_documents: Mapped[list["RawDocument"]] = relationship(back_populates="ingestion_run")


class IngestionError(Base):
    __tablename__ = "ingestion_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    raw_line: Mapped[str] = mapped_column(Text)
    error_category: Mapped[str] = mapped_column(String(20))
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["IngestionRun"] = relationship(back_populates="errors")
