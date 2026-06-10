from __future__ import annotations

import logging

from app.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging() -> None:
    """Configure the root logger to emit INFO+ records to stdout."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


def run_log_handler(run_id: int) -> logging.Handler:
    """Build a file handler capturing INFO+ records for a single ingestion run."""
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(settings.log_dir / f"ingestion_run_{run_id}.log")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler
