from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select

from app.models import Appointment, Clinic, ClinicPatient, Doctor, MedicationUse, Patient
from app.seed import seed_demo_clinic


@pytest.fixture
def demo(client) -> dict:
    with Session(client.app.state.engine) as session:
        clinic, _ = seed_demo_clinic(session)
        appointments = session.exec(select(Appointment).where(Appointment.clinic_id == clinic.id).order_by(Appointment.id)).all()
        return {"id": clinic.id, "appointment_ids": [item.id for item in appointments]}


@pytest.fixture
def other(client, demo) -> dict:
    # A second clinic with its own doctor, patient, and appointment.
    with Session(client.app.state.engine) as session:
        clinic = Clinic(name_ar="عيادة اختبار أخرى")
        patient = Patient(sex="male")
        session.add_all([clinic, patient])
        session.flush()
        doctor = Doctor(clinic_id=clinic.id, name_ar="د. اختبار")
        link = ClinicPatient(clinic_id=clinic.id, patient_id=patient.id, display_name_ar="مريض اختبار")
        session.add_all([doctor, link])
        session.flush()
        appointment = Appointment(clinic_id=clinic.id, doctor_id=doctor.id, clinic_patient_id=link.id, scheduled_at=datetime(2026, 11, 9, 6, tzinfo=timezone.utc))
        session.add(appointment)
        session.commit()
        return {"id": clinic.id, "appointment_id": appointment.id, "link_id": link.id, "doctor_id": doctor.id, "patient_id": patient.id}


def summary_url(clinic_id: int, appointment_id: int) -> str:
    return f"/clinics/{clinic_id}/appointments/{appointment_id}/summary"


# The right patient


def test_appointment_detail_shows_its_patient_and_doctor(client, demo):
    base = f"/clinics/{demo['id']}"
    appointment = client.get(f"{base}/appointments").json()[0]

    body = client.get(f"{base}/appointments/{appointment['id']}").json()

    assert body["appointment"] == appointment
    assert body["patient"]["id"] == appointment["clinic_patient_id"]
    assert body["doctor"]["id"] == appointment["doctor_id"]
    assert body["patient"]["display_name_ar"].startswith("مريض تجريبي")


def test_summary_opens_the_linked_patient(client, demo):
    for appointment_id in demo["appointment_ids"]:
        detail = client.get(f"/clinics/{demo['id']}/appointments/{appointment_id}").json()
        body = client.get(summary_url(demo["id"], appointment_id)).json()

        assert body["visit"] == detail
        assert body["clinic"]["id"] == demo["id"]
        assert body["risk_profile"]["patient_id"] == detail["patient"]["patient"]["id"]
        assert body["screening"]["patient_id"] == detail["patient"]["patient"]["id"]


def test_summary_is_marked_unvalidated_and_has_no_wearable_data(client, demo):
    body = client.get(summary_url(demo["id"], demo["appointment_ids"][0])).json()

    assert body["clinically_validated"] is False
    assert body["smartwatch_data_available"] is False
    assert body["screening"]["clinically_approved"] is False
    assert body["screening"]["auto_schedule_enabled"] is False


# Access across clinics


@pytest.mark.parametrize("suffix", ["", "/summary"])
def test_another_clinics_appointment_is_not_found(client, demo, other, suffix):
    into_demo = client.get(f"/clinics/{demo['id']}/appointments/{other['appointment_id']}{suffix}")
    into_other = client.get(f"/clinics/{other['id']}/appointments/{demo['appointment_ids'][0]}{suffix}")

    for response in (into_demo, into_other):
        assert response.status_code == 404
        assert "not found in clinic" in response.json()["detail"]


@pytest.mark.parametrize("path", ["/clinics/{demo}/appointments/9999", "/clinics/9999/appointments/{first}"])
@pytest.mark.parametrize("suffix", ["", "/summary"])
def test_missing_appointment_or_clinic_returns_404(client, demo, path, suffix):
    url = path.format(demo=demo["id"], first=demo["appointment_ids"][0]) + suffix

    assert client.get(url).status_code == 404


@pytest.mark.parametrize("foreign", ["link", "doctor"])
def test_an_appointment_pointing_into_another_clinic_is_refused(client, demo, other, foreign):
    with Session(client.app.state.engine) as session:
        local = session.exec(select(Appointment).where(Appointment.clinic_id == demo["id"])).first()
        corrupted = Appointment(
            clinic_id=demo["id"],
            doctor_id=other["doctor_id"] if foreign == "doctor" else local.doctor_id,
            clinic_patient_id=other["link_id"] if foreign == "link" else local.clinic_patient_id,
            scheduled_at=datetime(2026, 11, 9, 7, tzinfo=timezone.utc),
        )
        session.add(corrupted)
        session.commit()
        corrupted_id = corrupted.id

    for suffix in ("", "/summary"):
        assert client.get(f"/clinics/{demo['id']}/appointments/{corrupted_id}{suffix}").status_code == 404


def test_original_patients_never_appear_in_clinic_summaries(client, patient, demo):
    seen = set()
    for appointment_id in demo["appointment_ids"]:
        body = client.get(summary_url(demo["id"], appointment_id)).json()
        seen.add(body["visit"]["patient"]["patient"]["id"])

    linked = {item["patient"]["id"] for item in client.get(f"/clinics/{demo['id']}/patients").json()}
    assert seen <= linked
    assert patient["id"] not in seen


def test_summary_endpoints_are_read_only(client, demo):
    url = summary_url(demo["id"], demo["appointment_ids"][0])

    for method in ("post", "patch", "put", "delete"):
        assert client.request(method, url, json={}).status_code == 405


# Missing and recorded data


def first_patient(client, demo) -> tuple[int, int]:
    detail = client.get(f"/clinics/{demo['id']}/appointments/{demo['appointment_ids'][0]}").json()
    return detail["patient"]["patient"]["id"], demo["appointment_ids"][0]


def test_missing_profile_medications_and_history_stay_explicitly_empty(client, demo):
    body = client.get(summary_url(demo["id"], demo["appointment_ids"][0])).json()
    risk = body["risk_profile"]

    assert risk["stored"] is False
    assert risk["smoking_status"] == "unknown" and risk["bmi"] is None and risk["family_diabetes"] == "unknown"
    assert body["medications"] == []
    assert all(test["recorded_tests"] == [] for test in body["screening"]["tests"])
    assert body["screening"]["unmapped_records"] == []


def test_recorded_data_appears_in_the_summary(client, demo):
    patient_id, appointment_id = first_patient(client, demo)
    client.post(f"/patients/{patient_id}/risk-profile", json={"smoking_status": "never", "height_cm": 160, "weight_kg": 64, "family_diabetes": "yes"})
    client.post(f"/patients/{patient_id}/medications", json={"medication_id": "metformin", "dose_text": "500 mg", "start_date": "2021-01-10"})
    client.post(
        f"/patients/{patient_id}/screening-records",
        json={"test_id": "hba1c", "test_name": "HbA1c", "completed_on": "2026-03-02", "result": "7.1", "unit": "%", "source": "lab_report"},
    )

    body = client.get(summary_url(demo["id"], appointment_id)).json()

    assert body["risk_profile"]["bmi"] == 25.0
    assert body["risk_profile"]["family_diabetes"] == "yes"
    assert body["medications"] == [
        {
            "id": body["medications"][0]["id"],
            "medication_id": "metformin",
            "name_ar": "ميتفورمين",
            "generic_name": "Metformin",
            "drug_class": "biguanide",
            "dose_text": "500 mg",
            "start_date": "2021-01-10",
            "last_dose_change_date": None,
            "catalogue_status": "active",
        }
    ]
    hba1c = next(test for test in body["screening"]["tests"] if test["test_id"] == "hba1c")
    assert [(item["completed_on"], item["result"], item["unit"]) for item in hba1c["recorded_tests"]] == [("2026-03-02", "7.1", "%")]


def test_a_medication_outside_the_catalogue_keeps_its_id_and_no_invented_name(client, demo):
    patient_id, appointment_id = first_patient(client, demo)
    with Session(client.app.state.engine) as session:
        session.add(MedicationUse(patient_id=patient_id, medication_id="retired-drug", dose_text="10 mg"))
        session.commit()

    medication = client.get(summary_url(demo["id"], appointment_id)).json()["medications"][0]

    assert medication["medication_id"] == "retired-drug"
    assert medication["name_ar"] is None and medication["drug_class"] is None


def test_screening_in_the_summary_matches_the_patient_endpoint_exactly(client, demo):
    patient_id, appointment_id = first_patient(client, demo)
    client.post(f"/patients/{patient_id}/medications", json={"medication_id": "losartan", "dose_text": "50 mg"})

    summary = client.get(summary_url(demo["id"], appointment_id)).json()["screening"]

    assert summary == client.get(f"/patients/{patient_id}/screening-summary").json()


def test_opening_a_summary_changes_no_screening_output(client, demo):
    patient_id, appointment_id = first_patient(client, demo)
    before = client.get(f"/patients/{patient_id}/screening-preview").json()

    client.get(summary_url(demo["id"], appointment_id))

    assert client.get(f"/patients/{patient_id}/screening-preview").json() == before
