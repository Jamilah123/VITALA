from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import URL, Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers the tables on SQLModel.metadata)


def build_engine(database_path: Path) -> Engine:
    url = URL.create("sqlite", database=str(database_path))
    engine = create_engine(url, connect_args={"check_same_thread": False})

    # SQLite ignores foreign keys unless each connection turns them on.
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def init_db(engine: Engine, database_path: Path) -> None:
    """Create missing tables. Existing tables and rows are left untouched."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
