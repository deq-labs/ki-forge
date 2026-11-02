from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://kiforge:kiforge@localhost:5432/kiforge"
    app_env: str = "local"  # local | test | staging | production
    seed_path: Path = REPO_ROOT / "db" / "seed" / "program.json"


settings = Settings()
