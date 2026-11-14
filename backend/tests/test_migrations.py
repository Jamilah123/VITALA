"""Schema migrations: additive only, recorded, idempotent, and preceded by a backup."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, Settings
from app.main import create_app
from app.migrations import MIGRATIONS, applied_versions
from tests.conftest import seed_all

NEW_COLUMNS = {
    "appointment": ["appointment_type"],
    "screeningrecord": ["reference_range"],
    "patientriskprofile": [
        "information_source",
        "known_allergies",
        "family_cancer_history",
        "family_chronic_or_autoimmune_history",
        "known_genetic_findings",
    ],
}


def columns(path, table):
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def make_old_schema(path):
    """Turn a current database into the pre-2026-11-14 shape: drop the new columns and the record of migrations."""
    with sqlite3.connect(path) as connection:
        for table, names in NEW_COLUMNS.items():
            for name in names:
                connection.execute(f'ALTER TABLE "{table}" DROP COLUMN "{name}"')
        for table in ("allergy", "familycondition", "familyrelative", "geneticfinding", "patientinsurance", "schema_migration"):
            connection.execute(f'DROP TABLE "{table}"')


def test_a_new_database_records_every_migration_without_a_backup(settings):
    with TestClient(create_app(settings)) as client:
        assert applied_versions(client.app.state.engine) == sorted(m.version for m in MIGRATIONS)
    assert not settings.backup_dir.exists() or not any(settings.backup_dir.iterdir())
    for table, names in NEW_COLUMNS.items():
        assert set(names) <= columns(settings.database_path, table)


def test_an_old_database_gains_the_columns_and_keeps_every_row(settings):
    with TestClient(create_app(settings)) as first_run:
        ids = seed_all(first_run)
        patient_id = ids["synthetic_patient_id"]
        first_run.post(f"/patients/{patient_id}/risk-profile", json={"smoking_status": "never"})
        before = {
            "appointments": first_run.get(f"/clinics/{ids['clinic_id']}/appointments").json(),
            "patients": first_run.get(f"/clinics/{ids['clinic_id']}/patients").json(),
            "records": first_run.get(f"/patients/{ids['history_patient_id']}/screening-records").json(),
            "medications": first_run.get(f"/patients/{ids['history_patient_id']}/medications").json(),
        }
    make_old_schema(settings.database_path)
    with sqlite3.connect(settings.database_path) as connection:
        counts_before = {t: connection.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ("patient", "appointment", "screeningrecord", "medicationuse")}

    with TestClient(create_app(settings)) as second_run:
        assert applied_versions(second_run.app.state.engine) == sorted(m.version for m in MIGRATIONS)
        appointments = second_run.get(f"/clinics/{ids['clinic_id']}/appointments").json()
        # Every appointment that existed before is now in_person: VITALA had no virtual visits then.
        assert {a["appointment_type"] for a in appointments} == {"in_person"}
        strip = lambda items: [{k: v for k, v in item.items() if k not in ("appointment_type", "virtual_session_status")} for item in items]
        assert strip(appointments) == strip(before["appointments"])
        assert second_run.get(f"/clinics/{ids['clinic_id']}/patients").json() == before["patients"]
        records = second_run.get(f"/patients/{ids['history_patient_id']}/screening-records").json()
        assert [{k: v for k, v in r.items() if k != "reference_range"} for r in records] == [
            {k: v for k, v in r.items() if k != "reference_range"} for r in before["records"]
        ]
        assert all(r["reference_range"] is None for r in records)  # dropped values cannot come back; nothing is invented
        assert second_run.get(f"/patients/{ids['history_patient_id']}/medications").json() == before["medications"]
        profile = second_run.get(f"/patients/{patient_id}/risk-profile").json()
        assert profile["smoking_status"] == "never" and profile["known_allergies"] == "unknown"

    with sqlite3.connect(settings.database_path) as connection:
        counts_after = {t: connection.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in counts_before}
    assert counts_after == counts_before

    backups = list(settings.backup_dir.glob("*.db"))
    assert len(backups) == 1
    assert "appointment_type" not in columns(backups[0], "appointment")  # the backup is the pre-migration file
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM patient").fetchone()[0] == counts_before["patient"]


def test_restarting_applies_nothing_twice(settings):
    with TestClient(create_app(settings)):
        pass
    make_old_schema(settings.database_path)
    for _ in range(3):
        with TestClient(create_app(settings)):
            pass
    assert len(list(settings.backup_dir.glob("*.db"))) == 1
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0] == len(MIGRATIONS)


REAL_DB = BACKEND_DIR / "vitala.db"


@pytest.mark.skipif(not REAL_DB.exists(), reason="no local vitala.db")
def test_a_copy_of_the_real_development_database_migrates_without_losing_rows(tmp_path):
    copy = tmp_path / "vitala-copy.db"
    # Read the real file through SQLite's backup API; the original is never opened for writing.
    source = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    destination = sqlite3.connect(copy)
    source.backup(destination)
    destination.close()
    source.close()
    with sqlite3.connect(copy) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {t: connection.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall() for t in tables}

    settings = Settings(_env_file=None, database_path=copy, backup_dir=tmp_path / "backups")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json() == {"status": "ok", "database": "ok"}

    with sqlite3.connect(copy) as connection:
        for table, rows in before.items():
            after = connection.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
            # Rows are unchanged apart from new trailing columns with their defaults.
            assert [row[: len(rows[0])] for row in after] == rows if rows else after == []
