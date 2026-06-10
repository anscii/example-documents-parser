import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (ensure all models are registered on Base.metadata)
from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Author, Organization
from app.models.sentinels import UNKNOWN_DISPLAY_NAME, UNKNOWN_NORMALIZED_NAME


@pytest.fixture(autouse=True)
def _isolate_log_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")


@pytest.fixture()
def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    seed_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    seed_session.add(Author(name=UNKNOWN_DISPLAY_NAME, normalized_name=UNKNOWN_NORMALIZED_NAME))
    seed_session.add(Organization(name=UNKNOWN_DISPLAY_NAME, normalized_name=UNKNOWN_NORMALIZED_NAME))
    seed_session.commit()
    seed_session.close()

    return engine


@pytest.fixture()
def db_session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db_session(db_session_factory):
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session_factory, monkeypatch, tmp_path):
    def override_get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.services.ingestion_service.SessionLocal", db_session_factory)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
