from datetime import date, timedelta

import pytest
from sqlmodel import Session, select

from app.models import Appointment, Clinic, ClinicPatient, Patient, ScreeningRecord
from app.seed import seed_demo_clinic

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def error_fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [error["loc"][-1] for error in response.json()["detail"]]


@pytest.fixture
def demo(client) -> dict:
    with Session(client.app.state.engine) as session:
        clinic, _ = seed_demo_clinic(session)
        link = session.exec(select(ClinicPatient).where(ClinicPatient.clinic_id == clinic.id).order_by(ClinicPatient.id)).first()
        appointment = session.exec(select(Appointment).where(Appointment.clinic_patient_id == link.id)).first()
        return {"id": clinic.id, "link": link.id, "patient": link.patient_id, "appointment": appointment.id}


@pytest.fixture
def other(client, demo) -> dict:
    with Session(client.app.state.engine) as session:
        clinic = Clinic(name_ar="عيادة اختبار أخرى")
        patient = Patient(sex="male")
        session.add_all([clinic, patient])
        session.flush()
        link = ClinicPatient(clinic_id=clinic.id, patient_id=patient.id, display_name_ar="مريض اختبار")
        session.add(link)
        session.commit()
        return {"id": clinic.id, "link": link.id, "patient": patient.id}


@pytest.fixture
def url(demo) -> str:
    return f"/clinics/{demo['id']}/patients/{demo['link']}/screening-records"


def hba1c(**extra) -> dict:
    return {"test_id": "hba1c", "test_name": "HbA1c", "completed_on": "2026-03-02", "result": "7.3", "unit": "%", **extra}


@pytest.fixture
def saved(client, url) -> dict:
    response = client.post(url, json=hba1c(notes="نتيجة اختبارية"))
    assert response.status_code == 201, response.text
    return response.json()


# Valid submission and provenance


def test_a_clinic_result_is_saved_for_the_linked_patient_as_clinician_entered(saved, demo):
    assert saved["patient_id"] == demo["patient"]
    assert saved["source"] == "clinician_entered"
    assert (saved["test_id"], saved["completed_on"], saved["result"], saved["unit"], saved["notes"]) == (
        "hba1c", "2026-03-02", "7.3", "%", "نتيجة اختبارية",
    )


@pytest.mark.parametrize("field", ["source", "patient_id", "id"])
def test_the_client_cannot_set_source_or_patient(client, url, demo, other, field):
    value = {"source": "lab_report", "patient_id": other["patient"], "id": 1}[field]

    assert error_fields(client.post(url, json=hba1c(**{field: value}))) == [field]


def test_values_units_and_text_are_stored_exactly_as_entered(client, url):
    body = client.post(url, json=hba1c(result="  < 0.5 ", unit=" mL/min/1.73m² ", test_name=" eGFR ", test_id="egfr")).json()

    assert (body["result"], body["unit"], body["test_name"]) == ("< 0.5", "mL/min/1.73m²", "eGFR")


def test_an_examination_needs_no_result(client, url):
    body = client.post(url, json={"test_id": "eye_exam", "test_name": "فحص قاع العين", "completed_on": "2025-12-02"}).json()

    assert body["result"] is None and body["unit"] is None


# Invalid measurements, units, dates, and tests


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (hba1c(completed_on=TOMORROW), "completed_on"),
        (hba1c(completed_on="1970-01-01"), "completed_on"),
        (hba1c(completed_on="2026/03/02"), "completed_on"),
        (hba1c(completed_on="2026-02-30"), "completed_on"),
        (hba1c(result=None), "unit"),
        (hba1c(result="x" * 101), "result"),
        (hba1c(unit="x" * 51), "unit"),
        (hba1c(result="   "), "result"),
        (hba1c(test_name="  "), "test_name"),
        (hba1c(notes="x" * 1001), "notes"),
        (hba1c(test_id="hemoglobin"), "test_id"),
        (hba1c(test_id="HbA1c"), "test_id"),
        ({k: v for k, v in hba1c().items() if k != "completed_on"}, "completed_on"),
    ],
)
def test_invalid_results_are_rejected_and_not_saved(client, url, body, field):
    assert error_fields(client.post(url, json=body)) == [field]
    assert client.get(url).json() == []


# Cross-clinic and unlinked patients


@pytest.mark.parametrize("method", ["get", "post"])
def test_another_clinics_patient_cannot_be_read_or_written(client, demo, other, method):
    response = client.request(method, f"/clinics/{demo['id']}/patients/{other['link']}/screening-records", json=hba1c())

    assert response.status_code == 404
    assert "not found in clinic" in response.json()["detail"]
    with Session(client.app.state.engine) as session:
        assert session.exec(select(ScreeningRecord).where(ScreeningRecord.patient_id == other["patient"])).all() == []


@pytest.mark.parametrize("path", ["", "/screening-records"])
def test_patient_detail_and_history_are_clinic_scoped(client, demo, other, path):
    assert client.get(f"/clinics/{demo['id']}/patients/{demo['link']}{path}").status_code == 200
    assert client.get(f"/clinics/{demo['id']}/patients/{other['link']}{path}").status_code == 404
    assert client.get(f"/clinics/{other['id']}/patients/{demo['link']}{path}").status_code == 404
    assert client.get(f"/clinics/9999/patients/{demo['link']}{path}").status_code == 404


def test_an_unlinked_patient_cannot_be_reached_through_the_clinic(client, demo, patient):
    links = {item["id"] for item in client.get(f"/clinics/{demo['id']}/patients").json()}
    unused = max(links) + 100

    response = client.post(f"/clinics/{demo['id']}/patients/{unused}/screening-records", json=hba1c())

    assert response.status_code == 404
    assert client.get(f"/patients/{patient['id']}/screening-records").json() == []


def test_clinic_patient_detail_returns_the_linked_profile(client, demo):
    body = client.get(f"/clinics/{demo['id']}/patients/{demo['link']}").json()

    assert body["id"] == demo["link"]
    assert body["patient"]["id"] == demo["patient"]
    assert body["display_name_ar"].startswith("مريض تجريبي")


# One record, visible everywhere


def test_the_same_record_appears_in_clinic_patient_and_summary_views(client, url, demo, saved):
    clinic_view = client.get(url).json()
    patient_view = client.get(f"/patients/{demo['patient']}/screening-records").json()
    summary = client.get(f"/clinics/{demo['id']}/appointments/{demo['appointment']}/summary").json()
    summary_records = next(test for test in summary["screening"]["tests"] if test["test_id"] == "hba1c")["recorded_tests"]

    assert clinic_view == patient_view == summary_records == [saved]


def test_history_is_newest_first(client, url):
    for day in ("2025-01-10", "2026-02-01", "2025-07-20"):
        client.post(url, json=hba1c(completed_on=day, result=day))

    assert [item["completed_on"] for item in client.get(url).json()] == ["2026-02-01", "2025-07-20", "2025-01-10"]


# Duplicate submissions


def test_an_identical_resubmission_is_refused(client, url, saved):
    response = client.post(url, json=hba1c(notes="نتيجة اختبارية"))

    assert response.status_code == 409
    assert f"record {saved['id']}" in response.json()["detail"]
    assert len(client.get(url).json()) == 1


@pytest.mark.parametrize("change", [{"result": "7.4"}, {"completed_on": "2026-03-03"}, {"notes": None}, {"unit": "mmol/mol", "result": "56"}])
def test_records_that_differ_are_kept_even_on_the_same_day(client, url, saved, change):
    assert client.post(url, json=hba1c(notes="نتيجة اختبارية") | change).status_code == 201
    assert len(client.get(url).json()) == 2


def test_the_patient_endpoint_keeps_its_existing_behaviour(client, demo):
    body = hba1c(source="patient_reported")
    first = client.post(f"/patients/{demo['patient']}/screening-records", json=body)
    second = client.post(f"/patients/{demo['patient']}/screening-records", json=body)

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["source"] == "patient_reported"


def test_a_patient_reported_twin_does_not_block_a_clinician_entry(client, url, demo):
    client.post(f"/patients/{demo['patient']}/screening-records", json=hba1c(source="patient_reported"))

    assert client.post(url, json=hba1c()).status_code == 201


# Screening logic and original patients unchanged


def test_recording_results_never_changes_rule_evaluation(client, url, demo):
    before = client.get(f"/patients/{demo['patient']}/screening-preview").json()

    client.post(url, json=hba1c())
    client.post(url, json={"test_id": "eye_exam", "test_name": "فحص العين", "completed_on": "2025-12-02"})

    assert client.get(f"/patients/{demo['patient']}/screening-preview").json() == before


def test_clinic_results_never_touch_original_patients(client, url, patient):
    before = client.get(f"/patients/{patient['id']}").json()

    client.post(url, json=hba1c())

    assert client.get(f"/patients/{patient['id']}").json() == before
    assert client.get(f"/patients/{patient['id']}/screening-records").json() == []
