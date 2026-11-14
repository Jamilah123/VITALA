from pathlib import Path

from pydantic import SecretStr, field_validator
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
    # Copies of the database file are written here before a migration alters an existing table.
    backup_dir: Path = BACKEND_DIR / "db_backups"

    # The RAG chatbot runs as its own local process (see the root README.md). The backend only calls it.
    rag_url: str = "http://127.0.0.1:8001"
    rag_timeout_seconds: float = 60.0

    # Fernet key (urlsafe base64, 32 bytes) for national ID and insurance member numbers.
    # Without it, those two fields cannot be saved; everything else still works.
    field_encryption_key: SecretStr | None = None

    @field_validator("database_path", "medications_path", "backup_dir")
    @classmethod
    def anchor_to_backend_dir(cls, path: Path) -> Path:
        # Relative paths never depend on where the server was launched from.
        return path if path.is_absolute() else BACKEND_DIR / path
