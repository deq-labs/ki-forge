from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://kiforge:kiforge@localhost:5432/kiforge"
    app_env: str = "local"  # local | test | staging | production
    seed_path: Path = REPO_ROOT / "db" / "seed" / "program.json"
    library_path: Path = REPO_ROOT / "db" / "seed" / "exercise_library.json"
    # Where exercise photos are served from; an image path is appended. Empty = jsDelivr at the
    # library's pinned commit (fine for development; mirror to R2 before production, M6).
    exercise_images_base_url: str = ""
    # Clerk (sign-in). Without a secret key only the local dev header works (APP_ENV local/test).
    clerk_secret_key: str = ""
    clerk_authorized_parties: list[str] = []  # allowed "azp" origins for web sessions; empty = any


settings = Settings()
