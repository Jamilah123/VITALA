from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VITALA_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_path: Path = BACKEND_DIR / "vitala.db"
    medications_path: Path = BACKEND_DIR / "data" / "medications.json"
    cors_origins: list[str] = []

    @field_validator("database_path", "medications_path")
    @classmethod
    def anchor_to_backend_dir(cls, path: Path) -> Path:
        # Relative paths never depend on where the server was launched from.
        return path if path.is_absolute() else BACKEND_DIR / path
