from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class OffsetPage(BaseModel, Generic[T]):
    """Pagination shape for limit/offset-based endpoints (e.g. GET /ingestions)."""

    items: list[T]
    total: int
    limit: int
    offset: int


class Page(BaseModel, Generic[T]):
    """Pagination shape for page/page_size-based endpoints (e.g. GET /documents)."""

    items: list[T]
    total: int
    page: int
    page_size: int
