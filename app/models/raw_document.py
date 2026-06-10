from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.ingestion import IngestionRun


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), index=True, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ingestion_run: Mapped["IngestionRun"] = relationship(back_populates="raw_documents")
    document: Mapped["Document | None"] = relationship(back_populates="raw_document", uselist=False)
