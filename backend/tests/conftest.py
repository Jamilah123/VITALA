from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # Each test gets its own database file, and any local .env is ignored.
    return Settings(
        _env_file=None,
        database_path=tmp_path / "test.db",
        cors_origins=["http://frontend.test"],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


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
