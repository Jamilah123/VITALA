from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import URL, Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers the tables on SQLModel.metadata)
from app.migrations import run_migrations


def build_engine(database_path: Path) -> Engine:
    url = URL.create("sqlite", database=str(database_path))
    engine = create_engine(url, connect_args={"check_same_thread": False})

    # SQLite ignores foreign keys unless each connection turns them on.
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def init_db(engine: Engine, database_path: Path, backup_dir: Path | None = None) -> list[str]:
    """Create missing tables, then apply additive migrations. Existing rows are never changed or removed.

    Returns the migration versions applied in this call.
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    return run_migrations(engine, database_path, backup_dir or database_path.parent / "db_backups")


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
