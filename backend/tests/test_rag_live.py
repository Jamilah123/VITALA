"""Live end-to-end tests: backend -> real RAG service in rag/.

Skipped unless VITALA_RAG_LIVE_URL points at a running RAG service, for example:
    cd rag; ..\\rag\\.venv\\Scripts\\python.exe -m uvicorn vitala_rag.interfaces:app --port 8001
    $env:VITALA_RAG_LIVE_URL="http://127.0.0.1:8001"; .\\.venv\\Scripts\\python.exe -m pytest tests/test_rag_live.py
Works with any provider; in extractive mode nothing leaves the machine.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rag_client import RagClient
from tests.conftest import seed_all

LIVE_URL = os.environ.get("VITALA_RAG_LIVE_URL")
pytestmark = pytest.mark.skipif(not LIVE_URL, reason="VITALA_RAG_LIVE_URL not set")

MEDICATION_SOURCES = {"STATPEARLS-METFORMIN-2023", "STATPEARLS-ACEI-2025", "SA-MEDKB-2026", "FDA-LABEL-METFORMIN"}
ANSWERED = {"answered", "grounding_fallback"}


@pytest.fixture
def live(settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, rag_client=RagClient(LIVE_URL, timeout=120))) as client:
        yield client


def ask(client, question, patient_id=None):
    body = {"question": question} | ({"patient_id": patient_id} if patient_id else {})
    response = client.post("/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_metformin_kidney_question_is_answered_even_offline(live):
    body = ask(live, "Does metformin require kidney function monitoring?")
    assert body["status"] in ANSWERED and {c["source_id"] for c in body["citations"]} <= MEDICATION_SOURCES


def test_status(live):
    status = live.get("/chat/status").json()
    assert status["available"] is True and status["pipeline_version"]


@pytest.mark.parametrize(
    "question",
    [
        "Does metformin require kidney function monitoring?",
        "هل يحتاج الميتفورمين متابعة لوظائف الكلى؟",
        "What are common side effects of ACE inhibitors?",
        "ما هي الأعراض الجانبية الشائعة لمثبطات الإنزيم المحول؟",
    ],
)
def test_medication_questions_are_grounded_in_the_medication_sources(live, question):
    body = ask(live, question)
    if body["llm_provider"] == "extractive":
        # Offline mode has no LLM: no Arabic query translation and verbatim quotes only, so it may refuse.
        assert body["status"] in ANSWERED | {"insufficient_evidence"}, body
    else:
        assert body["status"] in ANSWERED, body
    if body["status"] in ANSWERED:
        assert body["citations"] and {c["source_id"] for c in body["citations"]} <= MEDICATION_SOURCES
    assert body["language"] == ("ar" if any("؀" <= ch <= "ۿ" for ch in question) else "en")


@pytest.mark.parametrize("question", ["كيف احجز موعد في VITALA؟", "How do I book an appointment in VITALA?"])
def test_app_questions_use_the_app_collection(live, question):
    body = ask(live, question)
    assert body["route"] == "app", body
    assert all(c["collection"] == "app" for c in body["citations"])


def test_out_of_scope_medication_is_declined(live):
    assert ask(live, "What are the side effects of atorvastatin?")["status"] == "declined_out_of_scope"


@pytest.mark.parametrize("question", ["Should I stop taking my lisinopril?", "هل أوقف الميتفورمين؟"])
def test_medication_change_requests_are_refused(live, question):
    assert ask(live, question)["status"] == "declined_personal_advice"


@pytest.mark.parametrize("question", ["I have crushing chest pain right now", "عندي ألم شديد في الصدر الآن وضيق تنفس"])
def test_emergencies_are_escalated(live, question):
    body = ask(live, question)
    assert body["status"] == "emergency_escalation" and "997" in body["display_text"] + body["answer"]


def test_synthetic_patient_screening_explanation(live):
    ids = seed_all(live)
    body = ask(live, "What is in my screening plan?", ids["history_patient_id"])
    assert body["patient_context"]["used"] is True
    assert body["status"] in {"answered", "patient_data_unavailable"}
    assert body["route"].startswith("patient")


def test_synthetic_patient_results_are_reported_not_interpreted(live):
    ids = seed_all(live)
    body = ask(live, "What was my latest HbA1c result?", ids["history_patient_id"])
    assert body["status"] == "answered", body
    assert "7.4" in body["answer"]
    assert any(c["collection"] == "patient_context" for c in body["citations"])


@pytest.mark.parametrize("language", ["en", "ar"])
def test_analyze_with_vitala(live, language):
    ids = seed_all(live)
    patient_id = ids["history_patient_id"]
    record = next(r for r in live.get(f"/patients/{patient_id}/screening-records").json() if r["test_id"] == "hba1c")
    response = live.post(f"/patients/{patient_id}/screening-records/{record['id']}/analysis", json={"language": language})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["explanation"]["language"] == language
    assert body["explanation"]["status"] in ANSWERED | {"insufficient_evidence"}
    assert "7.4" in body["explanation"]["answer"]
    assert body["result"]["reference_range"] == "4.0-5.6 % (synthetic lab range)"


def test_real_patients_stay_refused_with_the_live_service(live):
    patient = live.post("/patients", json={"sex": "female"}).json()
    assert live.post("/chat", json={"question": "my results", "patient_id": patient["id"]}).status_code == 403
