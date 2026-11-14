"""Versioned, additive schema migrations for existing SQLite databases.

SQLModel's create_all() creates missing tables but never adds a column to a
table that already exists. Each migration below adds what an older database is
missing. Migrations only add: they never drop, rename, rewrite or delete rows.

Every applied version is recorded in schema_migration. Before the first
migration that would alter an existing table, the whole database file is copied
to the backup directory with SQLite's online backup API.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Connection, Engine, inspect, text


@dataclass(frozen=True)
class AddColumn:
    table: str
    column: str
    ddl: str  # type, nullability and default, as SQLite DDL


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    columns: tuple[AddColumn, ...] = ()


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        "2026-11-14-01",
        "Appointment type: in_person or virtual. Existing appointments become in_person.",
        (AddColumn("appointment", "appointment_type", "VARCHAR(9) NOT NULL DEFAULT 'in_person'"),),
    ),
    Migration(
        "2026-11-14-02",
        "Laboratory reference range on screening records, nullable.",
        (AddColumn("screeningrecord", "reference_range", "VARCHAR"),),
    ),
    Migration(
        "2026-11-14-03",
        "Risk profile: information source and confirmed-negative status for allergies, family and genetic history.",
        (
            AddColumn("patientriskprofile", "information_source", "VARCHAR(20) NOT NULL DEFAULT 'unknown'"),
            AddColumn("patientriskprofile", "known_allergies", "VARCHAR(7) NOT NULL DEFAULT 'unknown'"),
            AddColumn("patientriskprofile", "family_cancer_history", "VARCHAR(7) NOT NULL DEFAULT 'unknown'"),
            AddColumn("patientriskprofile", "family_chronic_or_autoimmune_history", "VARCHAR(7) NOT NULL DEFAULT 'unknown'"),
            AddColumn("patientriskprofile", "known_genetic_findings", "VARCHAR(7) NOT NULL DEFAULT 'unknown'"),
        ),
    ),
    # New tables (allergy, familyrelative, familycondition, geneticfinding,
    # patientinsurance) are created by create_all and need no migration step.
    Migration("2026-11-14-04", "New tables: allergies, family history, genetic findings, insurance."),
)


def _missing_columns(connection: Connection, migration: Migration) -> list[AddColumn]:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing = []
    for item in migration.columns:
        if item.table not in tables:
            raise RuntimeError(f"Migration {migration.version}: table {item.table} does not exist")
        if item.column not in {column["name"] for column in inspector.get_columns(item.table)}:
            missing.append(item)
    return missing


def backup_database(database_path: Path, backup_dir: Path, label: str) -> Path:
    """Copy the database file with SQLite's backup API, which is safe while it is open."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{database_path.stem}-{stamp}-before-{label}.db"
    source = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def run_migrations(
    engine: Engine,
    database_path: Path,
    backup_dir: Path,
    migrations: tuple[Migration, ...] = MIGRATIONS,
    log: Callable[[str], None] = print,
) -> list[str]:
    """Apply pending migrations. Returns the versions applied in this call."""
    applied_now: list[str] = []
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migration (version VARCHAR PRIMARY KEY, applied_at VARCHAR NOT NULL)"))
        done = {row[0] for row in connection.execute(text("SELECT version FROM schema_migration"))}

    pending = [migration for migration in migrations if migration.version not in done]
    needs_alter = False
    with engine.connect() as connection:
        needs_alter = any(_missing_columns(connection, migration) for migration in pending)
    if needs_alter and database_path.exists():
        backup = backup_database(database_path, backup_dir, pending[0].version)
        log(f"Database backed up to {backup} before migrating")

    for migration in pending:
        with engine.begin() as connection:
            for item in _missing_columns(connection, migration):
                connection.execute(text(f'ALTER TABLE "{item.table}" ADD COLUMN "{item.column}" {item.ddl}'))
            connection.execute(
                text("INSERT INTO schema_migration (version, applied_at) VALUES (:version, :applied_at)"),
                {"version": migration.version, "applied_at": datetime.now(timezone.utc).isoformat()},
            )
        applied_now.append(migration.version)
    return applied_now


def applied_versions(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return [row[0] for row in connection.execute(text("SELECT version FROM schema_migration ORDER BY version"))]
