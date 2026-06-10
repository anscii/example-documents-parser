from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import documents, ingestions, processing, stats
from app.logging_config import configure_logging
from app.services import ingestion_service

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ingestion_service.resume_pending_runs()
    ingestion_service.drain_all_queues()
    yield


app = FastAPI(title="Document Intake and Review Service", lifespan=lifespan)

app.include_router(ingestions.router)
app.include_router(processing.router)
app.include_router(documents.router)
app.include_router(stats.router)
