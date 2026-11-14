"""Chatbot and Analyze-with-VITALA endpoints, against a fake RAG service.

These tests check what the backend sends and when it refuses. The real RAG
pipeline has its own suite in rag/tests and a live smoke test in test_rag_live.py.
"""

import json
from datetime import date

import pytest
from sqlmodel import Session

from app.models import PatientInsurance
from app.screening import full_years
from tests.conftest import seed_all

FORBIDDEN_KEYS = {"display_name_ar", "file_number", "national_id", "member_number", "insurer_name", "insurance_class", "allergies", "notes", "date_of_birth", "dose_text", "seed_key"}


def all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in all_keys(v)}
    return set()


@pytest.fixture
def ids(chat_client) -> dict:
    return seed_all(chat_client)


def test_status_reports_availability(chat_client, fake_rag):
    assert chat_client.get("/chat/status").json()["available"] is True
    fake_rag.down = True
    body = chat_client.get("/chat/status").json()
    assert body["available"] is False and body["patient_context_policy"] == "synthetic_demo_patients_only"


def test_general_question_sends_no_patient_data(chat_client, fake_rag):
    response = chat_client.post("/chat", json={"question": "What is metformin used for?"})
    assert response.status_code == 200
    body = response.json()
    assert body["display_text"] == "General information." and body["citations"][0]["source_id"] == "STATPEARLS-METFORMIN-2023"
    assert body["patient_context"] == {"used": False, "synthetic": False, "patient_id": None, "fields_sent": []}
    assert body["is_medical_advice"] is False
    assert fake_rag.requests == [{"question": "What is metformin used for?"}]


def test_arabic_question_is_forwarded_unchanged(chat_client, fake_rag):
    question = "هل يحتاج الميتفورمين متابعة لوظائف الكلى؟"
    assert chat_client.post("/chat", json={"question": question}).json()["language"] == "ar"
    assert fake_rag.requests[-1]["question"] == question


def test_real_patients_are_never_sent(chat_client, fake_rag):
    patient = chat_client.post("/patients", json={"sex": "female", "diabetes_status": "diagnosed"}).json()
    response = chat_client.post("/chat", json={"question": "What are my results?", "patient_id": patient["id"]})
    assert response.status_code == 403 and response.json()["detail"]["code"] == "patient_context_disabled"
    assert fake_rag.requests == []


def test_synthetic_patient_context_is_minimised(chat_client, fake_rag, ids):
    patient_id = ids["history_patient_id"]
    with Session(chat_client.app.state.engine) as session:
        session.add(PatientInsurance(patient_id=patient_id, coverage_status="insured", insurer_name="Synthetic Insurer", insurance_class="B", national_id_last4="0008"))
        session.commit()
    response = chat_client.post("/chat", json={"question": "What does my latest HbA1c mean?", "patient_id": patient_id})
    assert response.status_code == 200
    sent = fake_rag.requests[-1]["patient_context"]
    assert sent["is_synthetic"] is True and sent["patient_id"] == f"SYN-VITALA-P{patient_id}"
    assert not all_keys(sent) & FORBIDDEN_KEYS
    text = json.dumps(sent, ensure_ascii=False)
    assert "Synthetic Insurer" not in text and "Penicillin" not in text and "مريض تجريبي" not in text
    assert sent["age"] == full_years(date(1972, 5, 10), date.today()) and {m["name"] for m in sent["medications"]} == {"Metformin", "Lisinopril"}
    assert {r["test"] for r in sent["previous_results"]} == {"HbA1c", "eGFR", "Vitamin B12"}
    # The draft plan is labelled as draft and carries no status or due date.
    assert sent["screening_plan"] and all("status" not in item and "due_date" not in item for item in sent["screening_plan"])
    assert all("Not a recommendation" in item["reason"] for item in sent["screening_plan"])
    assert response.json()["patient_context"]["fields_sent"] == sorted(set(sent) - {"is_synthetic", "patient_id", "label", "data_as_of"})


def test_archived_medications_are_not_sent(chat_client, fake_rag, ids):
    from app.models import MedicationUse

    patient_id = ids["synthetic_patient_id"]
    with Session(chat_client.app.state.engine) as session:
        session.add(MedicationUse(patient_id=patient_id, medication_id="warfarin", dose_text="historical"))
        session.commit()
    chat_client.post("/chat", json={"question": "my medicines", "patient_id": patient_id})
    assert fake_rag.requests[-1]["patient_context"]["medications"] == []


def test_assistant_down_is_503_not_an_answer(chat_client, fake_rag, ids):
    fake_rag.down = True
    response = chat_client.post("/chat", json={"question": "hello"})
    assert response.status_code == 503 and response.json()["detail"]["code"] == "chat_unavailable"
    record = chat_client.get(f"/patients/{ids['history_patient_id']}/screening-records").json()[0]
    assert chat_client.post(f"/patients/{ids['history_patient_id']}/screening-records/{record['id']}/analysis", json={}).status_code == 503


def test_unknown_patient_is_404(chat_client):
    assert chat_client.post("/chat", json={"question": "x", "patient_id": 999}).status_code == 404


def test_question_is_validated(chat_client):
    assert chat_client.post("/chat", json={"question": ""}).status_code == 422
    assert chat_client.post("/chat", json={"question": "x" * 2001}).status_code == 422
    assert chat_client.post("/chat", json={"question": "x", "patient_context": {}}).status_code == 422


# ---------------------------------------------------------------- Analyze with VITALA


def records_by_test(client, patient_id) -> dict:
    return {r["test_id"]: r for r in client.get(f"/patients/{patient_id}/screening-records").json()}


@pytest.mark.parametrize(("language", "question"), [("en", "What does my latest HbA1c result mean?"), ("ar", "وش معنى آخر نتيجة HbA1c عندي؟")])
def test_analysis_sends_only_the_selected_result(chat_client, fake_rag, ids, language, question):
    patient_id = ids["history_patient_id"]
    record = records_by_test(chat_client, patient_id)["hba1c"]
    response = chat_client.post(f"/patients/{patient_id}/screening-records/{record['id']}/analysis", json={"language": language})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"] == {
        "record_id": record["id"], "test_id": "hba1c", "test_name": "HbA1c", "result": "7.4", "unit": "%",
        "completed_on": "2026-08-10", "reference_range": "4.0-5.6 % (synthetic lab range)", "source": "lab_report", "missing_fields": [],
    }
    assert body["interpreted_by_vitala"] is False and len(body["limitations"]) == 2
    sent = fake_rag.requests[-1]
    assert sent["question"] == question
    assert sent["patient_context"]["previous_results"] == [
        {"code": "HBA1C", "test": "HbA1c", "value": "7.4", "unit": "%", "date": "2026-08-10", "source": "lab_report"}
    ]
    assert "screening_plan" not in sent["patient_context"]
    assert not all_keys(sent) & FORBIDDEN_KEYS


def test_analysis_states_missing_range_and_unit_without_inventing_them(chat_client, fake_rag, ids):
    patient_id = ids["history_patient_id"]
    record = records_by_test(chat_client, patient_id)["vitamin_b12"]
    body = chat_client.post(f"/patients/{patient_id}/screening-records/{record['id']}/analysis", json={"language": "en"}).json()
    assert body["result"]["reference_range"] is None and body["result"]["missing_fields"] == ["reference_range"]
    assert any("reference range was not recorded" in item for item in body["limitations"])
    assert "reference" not in json.dumps(fake_rag.requests[-1]["patient_context"]).lower()


def test_analysis_of_a_record_without_a_value_is_refused(chat_client, fake_rag, ids):
    patient_id = ids["history_patient_id"]
    created = chat_client.post(f"/patients/{patient_id}/screening-records", json={"test_id": "eye_exam", "test_name": "Eye exam", "completed_on": "2026-05-01", "source": "patient_reported"}).json()
    assert chat_client.post(f"/patients/{patient_id}/screening-records/{created['id']}/analysis", json={}).status_code == 422
    assert fake_rag.requests == []


def test_analysis_never_crosses_patients(chat_client, fake_rag, ids):
    record = records_by_test(chat_client, ids["history_patient_id"])["hba1c"]
    response = chat_client.post(f"/patients/{ids['synthetic_patient_id']}/screening-records/{record['id']}/analysis", json={})
    assert response.status_code == 404 and fake_rag.requests == []


def test_analysis_refuses_non_synthetic_patients(chat_client, fake_rag):
    patient = chat_client.post("/patients", json={"sex": "male"}).json()
    record = chat_client.post(f"/patients/{patient['id']}/screening-records", json={"test_id": "hba1c", "test_name": "HbA1c", "completed_on": "2026-05-01", "result": "6.1", "unit": "%", "source": "lab_report"}).json()
    response = chat_client.post(f"/patients/{patient['id']}/screening-records/{record['id']}/analysis", json={})
    assert response.status_code == 403 and fake_rag.requests == []


def test_reference_range_is_optional_on_records(chat_client):
    patient = chat_client.post("/patients", json={"sex": "male"}).json()
    url = f"/patients/{patient['id']}/screening-records"
    created = chat_client.post(url, json={"test_id": "hba1c", "test_name": "HbA1c", "completed_on": "2026-05-01", "result": "6.1", "unit": "%", "reference_range": "4.0-5.6", "source": "lab_report"}).json()
    assert created["reference_range"] == "4.0-5.6"
    assert chat_client.patch(f"{url}/{created['id']}", json={"reference_range": None}).json()["reference_range"] is None
