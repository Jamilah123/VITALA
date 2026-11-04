from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.main import create_app
from app.models import Appointment, Clinic, ClinicPatient, Doctor, Patient
from app.seed import DEMO_APPOINTMENTS, DEMO_DOCTORS, DEMO_PATIENTS, seed_demo_clinic


@pytest.fixture
def demo(client) -> dict:
    with Session(client.app.state.engine) as session:
        clinic, created = seed_demo_clinic(session)
        assert created
        return {"id": clinic.id}


@pytest.fixture
def other_clinic(client, demo) -> dict:
    # A second clinic with its own data, to prove each clinic sees only its own rows.
    with Session(client.app.state.engine) as session:
        clinic = Clinic(name_ar="عيادة اختبار أخرى")
        patient = Patient(sex="male")
        session.add_all([clinic, patient])
        session.flush()
        doctor = Doctor(clinic_id=clinic.id, name_ar="د. اختبار")
        link = ClinicPatient(clinic_id=clinic.id, patient_id=patient.id, display_name_ar="مريض اختبار")
        session.add_all([doctor, link])
        session.flush()
        session.add(Appointment(clinic_id=clinic.id, doctor_id=doctor.id, clinic_patient_id=link.id, scheduled_at=datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)))
        session.commit()
        return {"id": clinic.id, "patient_id": patient.id}


# Seeding


def test_startup_creates_no_clinic(client):
    assert client.get("/clinics").json() == []


def test_seed_creates_one_demo_clinic_with_its_data(client, demo):
    base = f"/clinics/{demo['id']}"

    assert client.get("/clinics").json() == [
        {"id": demo["id"], "name_ar": "عيادة Vitala التجريبية", "city_ar": "الرياض", "time_zone": "Asia/Riyadh", "is_demo": True}
    ]
    assert len(client.get(f"{base}/doctors").json()) == len(DEMO_DOCTORS)
    assert len(client.get(f"{base}/patients").json()) == len(DEMO_PATIENTS)
    assert len(client.get(f"{base}/appointments").json()) == len(DEMO_APPOINTMENTS)


def test_seeding_twice_changes_nothing(client, demo):
    with Session(client.app.state.engine) as session:
        before = {model.__name__: len(session.exec(select(model)).all()) for model in (Clinic, Doctor, ClinicPatient, Appointment, Patient)}
        clinic, created = seed_demo_clinic(session)
        after = {model.__name__: len(session.exec(select(model)).all()) for model in (Clinic, Doctor, ClinicPatient, Appointment, Patient)}

    assert created is False
    assert clinic.id == demo["id"]
    assert after == before


def test_seed_never_touches_or_links_existing_patients(client, patient):
    with Session(client.app.state.engine) as session:
        seed_demo_clinic(session)

    assert client.get(f"/patients/{patient['id']}").json() == patient
    clinic_id = client.get("/clinics").json()[0]["id"]
    listed = [item["patient"]["id"] for item in client.get(f"/clinics/{clinic_id}/patients").json()]
    assert patient["id"] not in listed


def test_seed_markers_are_not_exposed(client, demo):
    base = f"/clinics/{demo['id']}"
    bodies = [client.get(path).json() for path in ("/clinics", f"{base}/doctors", f"{base}/patients", f"{base}/appointments")]

    assert "seed_key" not in str(bodies)


def test_demo_patients_are_clearly_synthetic(client, demo):
    for item in client.get(f"/clinics/{demo['id']}/patients").json():
        assert item["display_name_ar"].startswith("مريض تجريبي")
        assert item["file_number"].startswith("DEMO-")
    for doctor in client.get(f"/clinics/{demo['id']}/doctors").json():
        assert "تجريبي" in doctor["name_ar"]


def test_unknown_profile_values_stay_unknown_for_demo_patients(client, demo):
    patients = [item["patient"] for item in client.get(f"/clinics/{demo['id']}/patients").json()]

    assert any(patient["sex"] == "unknown" and patient["date_of_birth"] is None for patient in patients)
    assert any(patient["diabetes_status"] == "unknown" for patient in patients)


# Appointments


def test_appointments_are_ordered_and_consistent(client, demo):
    base = f"/clinics/{demo['id']}"
    appointments = client.get(f"{base}/appointments").json()
    doctor_ids = {doctor["id"] for doctor in client.get(f"{base}/doctors").json()}
    link_ids = {item["id"] for item in client.get(f"{base}/patients").json()}

    assert [item["scheduled_at"] for item in appointments] == sorted(item["scheduled_at"] for item in appointments)
    for item in appointments:
        assert item["clinic_id"] == demo["id"]
        assert item["doctor_id"] in doctor_ids
        assert item["clinic_patient_id"] in link_ids


def test_appointment_fields_have_the_expected_shape(client, demo):
    first = client.get(f"/clinics/{demo['id']}/appointments").json()[0]

    assert set(first) == {"id", "clinic_id", "doctor_id", "clinic_patient_id", "scheduled_at", "status", "booking_source", "visit_reason_ar"}
    assert first["scheduled_at"] == "2026-10-20T06:00:00Z"
    assert first["status"] in {"scheduled", "completed", "cancelled", "no_show"}
    assert first["booking_source"] in {"vitala", "clinic", "unknown"}


def test_appointments_include_every_status_for_the_demo(client, demo):
    statuses = {item["status"] for item in client.get(f"/clinics/{demo['id']}/appointments").json()}

    assert statuses == {"scheduled", "completed", "cancelled", "no_show"}


# Tenancy and separation


@pytest.mark.parametrize("resource", ["doctors", "patients", "appointments"])
def test_each_clinic_sees_only_its_own_rows(client, demo, other_clinic, resource):
    demo_rows = client.get(f"/clinics/{demo['id']}/{resource}").json()
    other_rows = client.get(f"/clinics/{other_clinic['id']}/{resource}").json()

    assert {row["clinic_id"] for row in demo_rows} == {demo["id"]}
    assert {row["clinic_id"] for row in other_rows} == {other_clinic["id"]}
    assert len(other_rows) == 1


def test_a_patient_appears_only_where_linked(client, demo, other_clinic):
    demo_patients = [item["patient"]["id"] for item in client.get(f"/clinics/{demo['id']}/patients").json()]

    assert other_clinic["patient_id"] not in demo_patients


@pytest.mark.parametrize("path", ["", "/doctors", "/patients", "/appointments"])
def test_unknown_clinic_returns_404(client, path):
    response = client.get(f"/clinics/999{path}")

    assert response.status_code == 404
    assert "Clinic 999" in response.json()["detail"]


def test_a_patient_links_to_a_clinic_only_once(client, demo):
    with Session(client.app.state.engine) as session:
        link = session.exec(select(ClinicPatient)).first()
        session.add(ClinicPatient(clinic_id=link.clinic_id, patient_id=link.patient_id, display_name_ar="نسخة"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_database_rejects_rows_for_a_missing_clinic(client):
    with Session(client.app.state.engine) as session:
        session.add(Doctor(clinic_id=999, name_ar="د. بلا عيادة"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_only_appointments_are_writable_and_never_deletable(client, demo):
    base = f"/clinics/{demo['id']}"
    first = client.get(f"{base}/appointments").json()[0]["id"]

    assert client.post("/clinics", json={"name_ar": "x"}).status_code == 405
    assert client.post(f"{base}/patients", json={}).status_code == 405
    assert client.post(f"{base}/doctors", json={}).status_code == 405
    assert client.delete(f"{base}/patients").status_code == 405
    assert client.delete(f"{base}/appointments/{first}").status_code == 405


# Existing databases


def test_existing_database_without_clinic_tables_keeps_its_records(settings):
    with TestClient(create_app(settings)) as first_run:
        patient = first_run.post("/patients", json={"sex": "female"}).json()
        with Session(first_run.app.state.engine) as session:
            for table in ("appointment", "clinicpatient", "doctor", "clinic"):
                session.connection().exec_driver_sql(f"DROP TABLE {table}")
            session.commit()

    with TestClient(create_app(settings)) as second_run:
        assert second_run.get(f"/patients/{patient['id']}").json() == patient
        assert second_run.get("/clinics").json() == []
