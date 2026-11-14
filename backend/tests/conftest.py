import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import Settings
from app.main import create_app
from app.rag_client import RagClient
from app.seed import seed_demo_clinic, seed_history_demo, seed_synthetic_patient


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # Each test gets its own database file, and any local .env is ignored.
    return Settings(
        _env_file=None,
        database_path=tmp_path / "test.db",
        backup_dir=tmp_path / "backups",
        cors_origins=["http://frontend.test"],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


class FakeRag:
    """Stands in for the RAG service. Records every request body it receives."""

    def __init__(self):
        self.requests: list[dict] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused")
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "llm_provider": "extractive", "pipeline_version": "0.2.0"})
        body = json.loads(request.content)
        self.requests.append(body)
        language = "ar" if any("؀" <= ch <= "ۿ" for ch in body["question"]) else "en"
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "status": "answered",
                "language": language,
                "answer": "General information [E1].",
                "citations": [
                    {"evidence_id": "E1", "chunk_id": "c1", "source_id": "STATPEARLS-METFORMIN-2023", "collection": "medication",
                     "title": "StatPearls: Metformin", "version": "2023", "citation": "StatPearls: Metformin, p. 4", "url": "", "pdf_page": 4}
                ],
                "retrieved_evidence_ids": ["E1"],
                "safety_flags": [],
                "collections_searched": ["medication"],
                "llm_provider": "extractive",
                "disclaimer": "General information, not a diagnosis.",
                "timings_ms": {},
                "pipeline_version": "0.2.0",
                "route": "patient+medical" if body.get("patient_context") else "medical",
                "patient_view": {"text": "General information.", "notices": ["Discuss with your clinician."], "sources": []},
            },
        )


@pytest.fixture
def fake_rag() -> FakeRag:
    return FakeRag()


@pytest.fixture
def rag_client(fake_rag: FakeRag) -> RagClient:
    return RagClient("http://rag.test", transport=httpx.MockTransport(fake_rag.handler))


@pytest.fixture
def chat_client(settings: Settings, rag_client: RagClient) -> Iterator[TestClient]:
    with TestClient(create_app(settings, rag_client=rag_client)) as test_client:
        yield test_client


@pytest.fixture
def key_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=tmp_path / "test.db",
        backup_dir=tmp_path / "backups",
        field_encryption_key=Fernet.generate_key().decode("ascii"),
    )


@pytest.fixture
def key_client(key_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(key_settings)) as test_client:
        yield test_client


def seed_all(test_client: TestClient) -> dict:
    """Run the real seed functions against the test database and return the synthetic ids."""
    with Session(test_client.app.state.engine) as session:
        synthetic, _ = seed_synthetic_patient(session)
        clinic, _ = seed_demo_clinic(session)
        history, _ = seed_history_demo(session, clinic)
        return {"synthetic_patient_id": synthetic.id, "clinic_id": clinic.id, "history_patient_id": history.id}


@pytest.fixture
def patient(client: TestClient) -> dict:
    response = client.post(
        "/patients",
        json={
            "date_of_birth": "1985-03-15",
            "sex": "female",
            "diabetes_status": "diagnosed",
            "diabetes_type": "type_2",
            "diabetes_diagnosis_date": "2020-06-01",
        },
    )
    assert response.status_code == 201
    return response.json()
