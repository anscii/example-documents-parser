import logging

from app.config import settings
from app.logging_config import run_log_handler


def test_run_log_handler_writes_to_per_run_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")

    handler = run_log_handler(42)
    try:
        logger = logging.getLogger("app.test_logging_config")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info("hello %s", "world")
        finally:
            logger.removeHandler(handler)
    finally:
        handler.close()

    log_file = tmp_path / "logs" / "ingestion_run_42.log"
    assert log_file.exists()
    assert "hello world" in log_file.read_text()


def test_run_log_handler_only_emits_info_and_above(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")

    handler = run_log_handler(7)
    try:
        logger = logging.getLogger("app.test_logging_config_levels")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            logger.debug("should not appear")
            logger.warning("should appear")
        finally:
            logger.removeHandler(handler)
    finally:
        handler.close()

    contents = (tmp_path / "logs" / "ingestion_run_7.log").read_text()
    assert "should not appear" not in contents
    assert "should appear" in contents
