from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import create_app
from app.screening_tests import SCREENING_TESTS

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def error_fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [error["loc"][-1] for error in response.json()["detail"]]


def hba1c(completed_on="2025-03-01", **extra) -> dict:
    return {"test_id": "hba1c", "test_name": "HbA1c", "completed_on": completed_on, "source": "lab_report", **extra}


@pytest.fixture
def records_url(patient) -> str:
    return f"/patients/{patient['id']}/screening-records"


@pytest.fixture
def record(client, records_url) -> dict:
    response = client.post(records_url, json=hba1c(result="7.1", unit="%", notes="Synthetic value"))
    assert response.status_code == 201
    return response.json()


# Test catalogue


def test_screening_tests_list_every_mapped_test(client):
    body = client.get("/screening-tests").json()

    assert [test["id"] for test in body] == list(SCREENING_TESTS)
    egfr = next(test for test in body if test["id"] == "egfr")
    assert egfr["rule_ids"] == ["DM04", "HTN04", "MED02"]
    assert "renal_potassium" in egfr["possible_overlap_test_ids"]
    assert {test["mapping_status"] for test in body} == {"draft_not_clinician_reviewed"}


# Recording history


def test_add_and_list(client, patient, records_url, record):
    assert record["patient_id"] == patient["id"]
    assert record["result"] == "7.1"
    assert record["unit"] == "%"
    assert client.get(records_url).json() == [record]


def test_list_is_empty_without_history(client, records_url):
    response = client.get(records_url)

    assert response.status_code == 200
    assert response.json() == []


def test_multiple_results_for_the_same_test_are_kept_newest_first(client, records_url):
    dates = ["2024-01-10", "2025-06-01", "2024-09-15"]
    for completed_on in dates:
        assert client.post(records_url, json=hba1c(completed_on, result="7.0", unit="%")).status_code == 201
    client.post(records_url, json=hba1c("2025-06-01", result="6.8", unit="%"))

    body = client.get(records_url).json()

    assert [item["completed_on"] for item in body] == ["2025-06-01", "2025-06-01", "2024-09-15", "2024-01-10"]
    assert [item["result"] for item in body[:2]] == ["6.8", "7.0"]


def test_minimal_record_leaves_result_and_notes_empty(client, records_url):
    body = client.post(records_url, json=hba1c()).json()

    assert body["result"] is None
    assert body["unit"] is None
    assert body["notes"] is None


@pytest.mark.parametrize("result", ["7.2", "< 0.5", "سلبي", "Normal per lab"])
def test_results_are_stored_verbatim(client, records_url, result):
    assert client.post(records_url, json=hba1c(result=f"  {result} ")).json()["result"] == result


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (hba1c() | {"test_id": "hemoglobin"}, "test_id"),
        (hba1c() | {"test_id": "HbA1c"}, "test_id"),
        (hba1c(TOMORROW), "completed_on"),
        (hba1c("1980-01-01"), "completed_on"),
        (hba1c("2025/03/01"), "completed_on"),
        (hba1c(unit="%"), "unit"),
        (hba1c(result=""), "result"),
        (hba1c() | {"source": "rumour"}, "source"),
        (hba1c() | {"test_name": "  "}, "test_name"),
        ({k: v for k, v in hba1c().items() if k != "completed_on"}, "completed_on"),
        ({k: v for k, v in hba1c().items() if k != "source"}, "source"),
        (hba1c() | {"due_on": "2026-01-01"}, "due_on"),
    ],
)
def test_add_rejects_invalid_records(client, records_url, body, field):
    assert error_fields(client.post(records_url, json=body)) == [field]
    assert client.get(records_url).json() == []


def test_patch_leaves_omitted_fields_unchanged(client, records_url, record):
    response = client.patch(f"{records_url}/{record['id']}", json={"result": "6.9"})

    assert response.status_code == 200
    assert response.json() == record | {"result": "6.9"}


def test_patch_null_clears_optional_fields(client, records_url, record):
    body = client.patch(f"{records_url}/{record['id']}", json={"notes": None, "unit": None, "result": None}).json()

    assert body["notes"] is None
    assert body["result"] is None
    assert body["completed_on"] == record["completed_on"]


def test_patch_is_judged_against_stored_values(client, records_url, record):
    assert error_fields(client.patch(f"{records_url}/{record['id']}", json={"result": None})) == ["unit"]
    assert client.get(records_url).json() == [record]


@pytest.mark.parametrize("field", ["completed_on", "source", "test_name"])
def test_patch_rejects_null_for_required_fields(client, records_url, record, field):
    assert error_fields(client.patch(f"{records_url}/{record['id']}", json={field: None})) == [field]


@pytest.mark.parametrize("field", ["test_id", "patient_id"])
def test_patch_cannot_change_test_or_owner(client, records_url, record, field):
    assert error_fields(client.patch(f"{records_url}/{record['id']}", json={field: "egfr"})) == [field]


def test_remove(client, records_url, record):
    assert client.delete(f"{records_url}/{record['id']}").status_code == 204
    assert client.get(records_url).json() == []
    assert client.delete(f"{records_url}/{record['id']}").status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/patients/999/screening-records", hba1c()),
        ("get", "/patients/999/screening-records", None),
        ("patch", "/patients/999/screening-records/1", {"result": "7"}),
        ("delete", "/patients/999/screening-records/1", None),
    ],
)
def test_operations_for_a_missing_patient_return_404(client, method, path, body):
    response = client.request(method, path, json=body)

    assert response.status_code == 404
    assert "Patient 999" in response.json()["detail"]


@pytest.mark.parametrize(("method", "body"), [("patch", {"result": "7"}), ("delete", None)])
def test_cannot_reach_another_patients_record(client, records_url, record, method, body):
    other = client.post("/patients", json={}).json()

    response = client.request(method, f"/patients/{other['id']}/screening-records/{record['id']}", json=body)

    assert response.status_code == 404
    assert client.get(records_url).json() == [record]


def test_birth_date_cannot_move_after_a_recorded_test(client, patient, records_url, record):
    url = f"/patients/{patient['id']}"
    client.patch(url, json={"diabetes_status": "unknown", "diabetes_type": "unknown", "diabetes_diagnosis_date": None})

    assert error_fields(client.patch(url, json={"date_of_birth": "2025-06-01"})) == ["date_of_birth"]
    assert client.patch(url, json={"date_of_birth": "2025-03-01"}).status_code == 200


# Existing databases


def test_existing_database_without_the_history_table_keeps_its_records(settings):
    with TestClient(create_app(settings)) as first_run:
        patient = first_run.post("/patients", json={"sex": "male"}).json()
        first_run.post(f"/patients/{patient['id']}/medications", json={"medication_id": "warfarin", "dose_text": "5 mg"})
        with Session(first_run.app.state.engine) as session:
            session.connection().exec_driver_sql("DROP TABLE screeningrecord")
            session.commit()

    with TestClient(create_app(settings)) as second_run:
        assert second_run.get(f"/patients/{patient['id']}").json() == patient
        assert second_run.get(f"/patients/{patient['id']}/medications").json()[0]["medication_id"] == "warfarin"
        added = second_run.post(f"/patients/{patient['id']}/screening-records", json=hba1c())
        assert added.status_code == 201
