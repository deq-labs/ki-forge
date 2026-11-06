"""M0 acceptance: schema migration matches the reference SQL, and the seed loads the expected counts."""

import importlib.util
import json

import pytest
from alembic import command
from sqlalchemy import Engine, text

from app.config import REPO_ROOT, settings
from tests.conftest import API_DIR, alembic_config

SCHEMA_FILE = REPO_ROOT / "db" / "0001_initial.sql"


def _load_migration(name: str):
    spec = importlib.util.spec_from_file_location(name, API_DIR / "migrations" / "versions" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0001_matches_reference_sql() -> None:
    reference = "\n".join(
        line
        for line in SCHEMA_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() not in ("BEGIN;", "COMMIT;")
    )
    embedded = _load_migration("0001_initial").SCHEMA_SQL
    assert embedded.strip() == reference.strip(), "edit db/0001_initial.sql and migration 0001 together"


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("exercises", 93),
        ("prescriptions", 25 + 57),  # main arc + Iron Tempo (#64)
        ("phases", 11 + 2),
        ("paths", 5),
        ("path_techniques", 8),
        ("badges", 6),
        ("session_templates", 6 + 9),
        ("programs", 2),
    ],
)
def test_seed_counts(db_engine: Engine, table: str, expected: int) -> None:
    with db_engine.connect() as conn:
        assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == expected


def test_only_engine_uses_path_conditioning(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        codes = conn.execute(
            text("SELECT code FROM session_templates WHERE uses_path_conditioning ORDER BY code")
        ).scalars()
        assert list(codes) == ["engine"]


def test_garage_swaps_and_path_conditioning_resolved(db_engine: Engine) -> None:
    seed = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    expected_swaps = sum(1 for e in seed["exercises"] if e["swap"])
    with db_engine.connect() as conn:
        swaps = conn.execute(text("SELECT count(*) FROM exercises WHERE swap_exercise_id IS NOT NULL"))
        assert swaps.scalar_one() == expected_swaps
        missing = conn.execute(text("SELECT count(*) FROM paths WHERE conditioning_exercise_id IS NULL"))
        assert missing.scalar_one() == 0


def test_downgrade_and_upgrade_round_trip(db_url: str, db_engine: Engine) -> None:
    cfg = alembic_config(db_url)
    command.downgrade(cfg, "base")
    with db_engine.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' "
                "AND table_name <> 'alembic_version'"
            )
        ).scalar_one()
    assert tables == 0
    command.upgrade(cfg, "head")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM exercises")).scalar_one() == 93
        assert conn.execute(text("SELECT count(*) FROM programs")).scalar_one() == 2
