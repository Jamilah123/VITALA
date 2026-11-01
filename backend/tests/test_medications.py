import json
from datetime import date, timedelta

import pytest

from app.catalogue import load_catalogue
from app.config import BACKEND_DIR

DATA_DIR = BACKEND_DIR / "data"
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def read_data(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def error_fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [error["loc"][-1] for error in response.json()["detail"]]


@pytest.fixture
def uses_url(patient) -> str:
    return f"/patients/{patient['id']}/medications"


@pytest.fixture
def use(client, uses_url) -> dict:
    response = client.post(
        uses_url,
        json={
            "medication_id": "metformin",
            "dose_text": "500 mg twice daily",
            "start_date": "2021-01-10",
            "last_dose_change_date": "2022-05-20",
        },
    )
    assert response.status_code == 201
    return response.json()


# Catalogue


def test_catalogue_matches_the_source_file_exactly(client):
    response = client.get("/medications")

    assert response.status_code == 200
    assert response.json() == read_data("medications.json")


def test_catalogue_medication_by_id(client):
    body = client.get("/medications/warfarin").json()

    assert body["name_ar"] == "وارفارين"
    assert body["identity_evidence"] == [{"source_id": "S08", "locator": "PDF p. 3"}]


def test_catalogue_unknown_id_returns_404(client):
    assert client.get("/medications/aspirin").status_code == 404


def test_catalogue_references_resolve_to_copied_data():
    sources = {source["id"] for source in read_data("sources.json")}
    rules = {rule["id"] for rule in read_data("medication_monitoring.json")}

    for medication in read_data("medications.json"):
        assert {item["source_id"] for item in medication["identity_evidence"]} <= sources
        assert set(medication["monitoring_rule_ids"]) <= rules


@pytest.mark.parametrize("name", ["disease_rules.json", "medication_monitoring.json"])
def test_copied_rules_are_still_drafts_with_scheduling_off(name):
    for rule in read_data(name):
        assert rule["clinical_status"] == "draft_not_clinician_reviewed"
        assert rule["auto_schedule_enabled"] is False
        assert rule["reviewer"] is None


def test_catalogue_loader_rejects_duplicate_ids(tmp_path):
    entry = read_data("medications.json")[0]
    path = tmp_path / "medications.json"
    path.write_text(json.dumps([entry, entry]), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate"):
        load_catalogue(path)


# Medication use


def test_add_and_list(client, patient, uses_url, use):
    assert use["patient_id"] == patient["id"]
    assert use["medication_id"] == "metformin"
    assert client.get(uses_url).json() == [use]


def test_list_is_empty_for_a_patient_without_medications(client, uses_url):
    response = client.get(uses_url)

    assert response.status_code == 200
    assert response.json() == []


def test_add_with_only_required_fields_leaves_dates_unknown(client, uses_url):
    body = client.post(uses_url, json={"medication_id": "losartan", "dose_text": "50 mg"}).json()

    assert body["start_date"] is None
    assert body["last_dose_change_date"] is None


def test_add_rejects_id_outside_the_catalogue(client, uses_url):
    response = client.post(uses_url, json={"medication_id": "aspirin", "dose_text": "81 mg"})

    assert error_fields(response) == ["medication_id"]
    assert client.get(uses_url).json() == []


def test_catalogue_id_match_is_exact(client, uses_url):
    response = client.post(uses_url, json={"medication_id": "Metformin", "dose_text": "500 mg"})

    assert error_fields(response) == ["medication_id"]


def test_adding_the_same_medication_twice_returns_409(client, uses_url, use):
    response = client.post(uses_url, json={"medication_id": "metformin", "dose_text": "850 mg"})

    assert response.status_code == 409
    assert client.get(uses_url).json() == [use]


@pytest.mark.parametrize("dose", ["", "   ", "x" * 201, None])
def test_add_rejects_blank_or_oversized_dose(client, uses_url, dose):
    response = client.post(uses_url, json={"medication_id": "metformin", "dose_text": dose})

    assert error_fields(response) == ["dose_text"]


def test_dose_text_is_kept_in_arabic_and_trimmed(client, uses_url):
    body = client.post(uses_url, json={"medication_id": "metformin", "dose_text": "  500 ملغ مرتين يوميًا "}).json()

    assert body["dose_text"] == "500 ملغ مرتين يوميًا"


@pytest.mark.parametrize(
    ("dates", "field"),
    [
        ({"start_date": TOMORROW}, "start_date"),
        ({"last_dose_change_date": TOMORROW}, "last_dose_change_date"),
        ({"start_date": "1980-01-01"}, "start_date"),
        ({"last_dose_change_date": "1980-01-01"}, "last_dose_change_date"),
        ({"start_date": "2022-01-01", "last_dose_change_date": "2021-01-01"}, "last_dose_change_date"),
        ({"start_date": "not-a-date"}, "start_date"),
    ],
)
def test_add_rejects_invalid_or_inconsistent_dates(client, uses_url, dates, field):
    response = client.post(uses_url, json={"medication_id": "metformin", "dose_text": "500 mg", **dates})

    assert error_fields(response) == [field]


def test_patch_leaves_omitted_fields_unchanged(client, uses_url, use):
    response = client.patch(f"{uses_url}/{use['id']}", json={"dose_text": "850 mg"})

    assert response.status_code == 200
    assert response.json() == use | {"dose_text": "850 mg"}


def test_patch_null_clears_a_date_while_omitted_date_stays(client, uses_url, use):
    body = client.patch(f"{uses_url}/{use['id']}", json={"last_dose_change_date": None}).json()

    assert body["last_dose_change_date"] is None
    assert body["start_date"] == use["start_date"]


def test_patch_rejects_null_dose(client, uses_url, use):
    assert error_fields(client.patch(f"{uses_url}/{use['id']}", json={"dose_text": None})) == ["dose_text"]


def test_patch_is_judged_against_stored_dates(client, uses_url, use):
    response = client.patch(f"{uses_url}/{use['id']}", json={"start_date": "2023-01-01"})

    assert error_fields(response) == ["last_dose_change_date"]
    assert client.get(uses_url).json() == [use]


@pytest.mark.parametrize("field", ["medication_id", "patient_id"])
def test_patch_cannot_change_medication_or_owner(client, uses_url, use, field):
    response = client.patch(f"{uses_url}/{use['id']}", json={field: "losartan"})

    assert error_fields(response) == [field]


def test_remove(client, uses_url, use):
    assert client.delete(f"{uses_url}/{use['id']}").status_code == 204
    assert client.get(uses_url).json() == []
    assert client.delete(f"{uses_url}/{use['id']}").status_code == 404


def test_removed_medication_can_be_added_again(client, uses_url, use):
    client.delete(f"{uses_url}/{use['id']}")

    response = client.post(uses_url, json={"medication_id": "metformin", "dose_text": "850 mg"})

    assert response.status_code == 201


# Missing records


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/patients/999/medications", {"medication_id": "metformin", "dose_text": "500 mg"}),
        ("get", "/patients/999/medications", None),
        ("patch", "/patients/999/medications/1", {"dose_text": "500 mg"}),
        ("delete", "/patients/999/medications/1", None),
    ],
)
def test_operations_for_a_missing_patient_return_404(client, method, path, body):
    response = client.request(method, path, json=body)

    assert response.status_code == 404
    assert "Patient 999" in response.json()["detail"]


@pytest.mark.parametrize(("method", "body"), [("patch", {"dose_text": "500 mg"}), ("delete", None)])
def test_operations_for_a_missing_medication_use_return_404(client, uses_url, method, body):
    assert client.request(method, f"{uses_url}/999", json=body).status_code == 404


@pytest.mark.parametrize(("method", "body"), [("patch", {"dose_text": "1 g"}), ("delete", None)])
def test_cannot_reach_another_patients_medication_use(client, uses_url, use, method, body):
    other = client.post("/patients", json={}).json()

    response = client.request(method, f"/patients/{other['id']}/medications/{use['id']}", json=body)

    assert response.status_code == 404
    assert client.get(uses_url).json() == [use]
