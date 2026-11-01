from datetime import date, timedelta

import pytest

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def error_fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [error["loc"][-1] for error in response.json()["detail"]]


def test_create_and_read_full_profile(client, patient):
    response = client.get(f"/patients/{patient['id']}")

    assert response.status_code == 200
    assert response.json() == {
        "id": patient["id"],
        "date_of_birth": "1985-03-15",
        "sex": "female",
        "diabetes_status": "diagnosed",
        "diabetes_type": "type_2",
        "diabetes_diagnosis_date": "2020-06-01",
        "hypertension_status": "unknown",
        "hypertension_diagnosis_date": None,
    }


def test_missing_information_is_stored_as_unknown_not_negative(client):
    body = client.post("/patients", json={}).json()

    assert body["sex"] == "unknown"
    assert body["diabetes_status"] == "unknown"
    assert body["diabetes_type"] == "unknown"
    assert body["hypertension_status"] == "unknown"
    assert body["date_of_birth"] is None
    assert body["diabetes_diagnosis_date"] is None
    assert "not_diagnosed" not in body.values()


def test_not_diagnosed_can_be_stated_explicitly(client):
    body = client.post("/patients", json={"hypertension_status": "not_diagnosed"}).json()

    assert body["hypertension_status"] == "not_diagnosed"
    assert body["diabetes_status"] == "unknown"


def test_read_missing_patient_returns_404(client):
    assert client.get("/patients/999").status_code == 404


def test_update_missing_patient_returns_404(client):
    assert client.patch("/patients/999", json={"sex": "male"}).status_code == 404


def test_patch_leaves_omitted_fields_unchanged(client, patient):
    response = client.patch(f"/patients/{patient['id']}", json={"hypertension_status": "diagnosed"})

    assert response.status_code == 200
    assert response.json() == patient | {"hypertension_status": "diagnosed"}


def test_patch_null_clears_a_date_while_omitted_date_stays(client, patient):
    response = client.patch(f"/patients/{patient['id']}", json={"diabetes_diagnosis_date": None})

    assert response.status_code == 200
    body = response.json()
    assert body["diabetes_diagnosis_date"] is None
    assert body["date_of_birth"] == "1985-03-15"
    assert client.get(f"/patients/{patient['id']}").json()["diabetes_diagnosis_date"] is None


def test_empty_patch_changes_nothing(client, patient):
    response = client.patch(f"/patients/{patient['id']}", json={})

    assert response.status_code == 200
    assert response.json() == patient


@pytest.mark.parametrize("field", ["sex", "diabetes_status", "diabetes_type", "hypertension_status"])
def test_patch_rejects_null_for_fields_that_have_unknown(client, patient, field):
    response = client.patch(f"/patients/{patient['id']}", json={field: None})

    assert error_fields(response) == [field]


def test_status_can_return_to_unknown_only_with_its_dependent_fields(client, patient):
    url = f"/patients/{patient['id']}"

    rejected = client.patch(url, json={"diabetes_status": "unknown"})
    assert sorted(error_fields(rejected)) == ["diabetes_diagnosis_date", "diabetes_type"]
    assert client.get(url).json() == patient

    accepted = client.patch(
        url,
        json={"diabetes_status": "unknown", "diabetes_type": "unknown", "diabetes_diagnosis_date": None},
    )
    assert accepted.status_code == 200
    assert accepted.json()["diabetes_status"] == "unknown"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"date_of_birth": TOMORROW}, "date_of_birth"),
        ({"diabetes_status": "diagnosed", "diabetes_diagnosis_date": TOMORROW}, "diabetes_diagnosis_date"),
        ({"hypertension_status": "diagnosed", "hypertension_diagnosis_date": TOMORROW}, "hypertension_diagnosis_date"),
        (
            {"date_of_birth": "2000-01-01", "diabetes_status": "diagnosed", "diabetes_diagnosis_date": "1999-12-31"},
            "diabetes_diagnosis_date",
        ),
        (
            {"date_of_birth": "2000-01-01", "hypertension_status": "diagnosed", "hypertension_diagnosis_date": "1999-12-31"},
            "hypertension_diagnosis_date",
        ),
        ({"diabetes_diagnosis_date": "2020-01-01"}, "diabetes_diagnosis_date"),
        ({"diabetes_status": "not_diagnosed", "diabetes_diagnosis_date": "2020-01-01"}, "diabetes_diagnosis_date"),
        ({"hypertension_diagnosis_date": "2020-01-01"}, "hypertension_diagnosis_date"),
        ({"diabetes_type": "type_1"}, "diabetes_type"),
        ({"date_of_birth": "2023-02-30"}, "date_of_birth"),
        ({"date_of_birth": "15/03/1985"}, "date_of_birth"),
        ({"date_of_birth": "1985-03-15T10:00:00"}, "date_of_birth"),
        ({"date_of_birth": 479692800}, "date_of_birth"),
        ({"sex": "other"}, "sex"),
        ({"diabetes_typo": "type_1"}, "diabetes_typo"),
    ],
)
def test_create_rejects_invalid_or_inconsistent_values(client, body, field):
    assert error_fields(client.post("/patients", json=body)) == [field]


def test_patch_is_judged_against_stored_values(client, patient):
    response = client.patch(f"/patients/{patient['id']}", json={"date_of_birth": "2021-01-01"})

    assert error_fields(response) == ["diabetes_diagnosis_date"]
    assert client.get(f"/patients/{patient['id']}").json() == patient


def test_birth_date_cannot_move_after_recorded_medication_dates(client, patient):
    url = f"/patients/{patient['id']}"
    client.post(f"{url}/medications", json={"medication_id": "metformin", "dose_text": "500 mg", "start_date": "2010-01-01"})
    client.patch(url, json={"diabetes_status": "unknown", "diabetes_type": "unknown", "diabetes_diagnosis_date": None})

    assert error_fields(client.patch(url, json={"date_of_birth": "2015-01-01"})) == ["date_of_birth"]
    assert client.patch(url, json={"date_of_birth": "2009-01-01"}).status_code == 200


def test_today_is_an_accepted_date(client):
    today = date.today().isoformat()
    response = client.post(
        "/patients",
        json={"date_of_birth": today, "diabetes_status": "diagnosed", "diabetes_diagnosis_date": today},
    )

    assert response.status_code == 201
