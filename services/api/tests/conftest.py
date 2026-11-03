"""Test fixtures. DB tests run against a throwaway `<db>_test` database on the same server."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings
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
