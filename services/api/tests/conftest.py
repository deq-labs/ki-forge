"""Test fixtures. DB tests run against a throwaway `<db>_test` database on the same server."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.main import app
from app.rules.program import Program, load_program

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def program() -> Program:
    return load_program(settings.seed_path)


def _test_url() -> str:
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    return cfg


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    test_url = _test_url()
    name = make_url(test_url).database
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        command.upgrade(alembic_config(test_url), "head")
        yield test_url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def db_engine(db_url: str) -> Iterator[Engine]:
    engine = create_engine(db_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test; `commit()` inside the app becomes a savepoint."""
    with db_engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


DEV_USER = "joe@example.com"


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """API client signed in as DEV_USER through the local dev header."""
    app.dependency_overrides[get_session] = lambda: db
    try:
        with TestClient(app, headers={"X-Dev-User": DEV_USER}) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
