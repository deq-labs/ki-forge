from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The schema is raw SQL (see versions/0001_initial.py), so there is no autogenerate metadata yet.
target_metadata = None


def url() -> str:
    return config.attributes.get("database_url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
