"""The ORM models match the migrated schema (db/0001_initial.sql), table by table and column by column."""

from sqlalchemy import Engine, inspect

from app.models import Base


def test_models_cover_every_table(db_engine: Engine) -> None:
    tables = set(inspect(db_engine).get_table_names()) - {"alembic_version"}
    assert set(Base.metadata.tables) == tables


def test_model_columns_match_schema(db_engine: Engine) -> None:
    insp = inspect(db_engine)
    for name, table in Base.metadata.tables.items():
        db_cols = {c["name"]: c for c in insp.get_columns(name)}
        assert set(table.columns.keys()) == set(db_cols), name
        for col in table.columns:
            assert col.nullable == db_cols[col.name]["nullable"], f"{name}.{col.name} nullable"
        db_pk = set(insp.get_pk_constraint(name)["constrained_columns"])
        assert {c.name for c in table.primary_key} == db_pk, f"{name} primary key"
