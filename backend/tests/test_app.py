import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import BACKEND_DIR, Settings
from app.main import create_app
from app.models import MedicationUse, Patient
from app.seed import SEED_KEY, seed_synthetic_patient


def file_state(path):
    return (path.stat().st_size, path.stat().st_mtime_ns) if path.exists() else None


# Health and docs


def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_docs_are_available(client):
    assert client.get("/docs").status_code == 200


# CORS


def test_cors_allows_only_configured_origins(client):
    def preflight(origin):
        return client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})

    allowed = preflight("http://frontend.test")
    assert allowed.headers["access-control-allow-origin"] == "http://frontend.test"

    blocked = preflight("http://elsewhere.test")
    assert "access-control-allow-origin" not in blocked.headers


def test_cors_origins_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("VITALA_CORS_ORIGINS", '["http://localhost:5173"]')

    assert Settings(_env_file=None).cors_origins == ["http://localhost:5173"]


# Database location


def test_default_database_location_ignores_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("VITALA_DATABASE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    assert Settings(_env_file=None).database_path == BACKEND_DIR / "vitala.db"


def test_relative_database_path_is_anchored_to_the_backend_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert Settings(_env_file=None, database_path="local/dev.db").database_path == BACKEND_DIR / "local" / "dev.db"


# Persistence


def test_records_persist_across_database_sessions(client, patient):
    use = client.post(
        f"/patients/{patient['id']}/medications",
        json={"medication_id": "lisinopril", "dose_text": "50 mg", "start_date": "2021-02-03"},
    ).json()

    with Session(client.app.state.engine) as session:
        stored_patient = session.get(Patient, patient["id"])
        stored_use = session.get(MedicationUse, use["id"])
        assert stored_patient.date_of_birth.isoformat() == "1985-03-15"
        assert stored_use.dose_text == "50 mg"
        assert stored_use.start_date.isoformat() == "2021-02-03"


def test_records_persist_when_the_app_restarts(settings):
    with TestClient(create_app(settings)) as first_run:
        patient = first_run.post("/patients", json={"sex": "male"}).json()
        first_run.post(f"/patients/{patient['id']}/medications", json={"medication_id": "lisinopril", "dose_text": "5 mg"})

    with TestClient(create_app(settings)) as second_run:
        assert second_run.get(f"/patients/{patient['id']}").json() == patient
        assert second_run.get(f"/patients/{patient['id']}/medications").json()[0]["medication_id"] == "lisinopril"


def test_dates_are_stored_as_date_columns(client, patient):
    with Session(client.app.state.engine) as session:
        columns = session.connection().exec_driver_sql("PRAGMA table_info(patient)").all()

    types = {column[1]: column[2] for column in columns}
    assert types["date_of_birth"] == "DATE"
    assert types["diabetes_diagnosis_date"] == "DATE"


def test_database_rejects_medication_use_without_a_patient(client):
    with Session(client.app.state.engine) as session:
        session.add(MedicationUse(patient_id=999, medication_id="metformin", dose_text="500 mg"))
        with pytest.raises(IntegrityError):
            session.commit()


# Seeding


def test_startup_does_not_seed(client):
    with Session(client.app.state.engine) as session:
        assert session.exec(select(Patient)).all() == []


def test_seed_creates_one_patient_and_never_overwrites(client):
    with Session(client.app.state.engine) as session:
        patient, created = seed_synthetic_patient(session)
        assert created is True
        patient_id = patient.id

    client.patch(f"/patients/{patient_id}", json={"sex": "unknown"})

    with Session(client.app.state.engine) as session:
        again, created = seed_synthetic_patient(session)
        assert created is False
        assert again.id == patient_id
        assert session.exec(select(Patient).where(Patient.seed_key == SEED_KEY)).one().sex == "unknown"
        assert len(session.exec(select(Patient)).all()) == 1


def test_seed_marker_is_not_exposed_by_the_api(client):
    with Session(client.app.state.engine) as session:
        patient_id = seed_synthetic_patient(session)[0].id

    assert "seed_key" not in client.get(f"/patients/{patient_id}").json()


# Test isolation


def test_tests_never_touch_the_development_database(client, settings, tmp_path):
    development_db = Settings(_env_file=None, database_path="vitala.db").database_path
    before = file_state(development_db)

    client.post("/patients", json={"sex": "female"})

    assert settings.database_path.parent == tmp_path
    assert settings.database_path != development_db
    assert client.app.state.engine.url.database == str(tmp_path / "test.db")
    assert (tmp_path / "test.db").exists()
    assert file_state(development_db) == before


def test_each_test_starts_with_an_empty_database(client):
    assert client.get("/patients/1").status_code == 404
