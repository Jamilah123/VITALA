import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import BACKEND_DIR
from app.main import create_app

UNKNOWN_PROFILE = {
    "stored": False,
    "smoking_status": "unknown",
    "height_cm": None,
    "weight_kg": None,
    "bmi": None,
    "activity_minutes_per_week": None,
    "raised_lipids": "unknown",
    "pregnancy_status": "unknown",
    "family_diabetes": "unknown",
    "family_heart_disease": "unknown",
    "family_breast_cancer": "unknown",
    "family_colorectal_cancer": "unknown",
    "information_source": "unknown",
    "known_allergies": "unknown",
    "family_cancer_history": "unknown",
    "family_chronic_or_autoimmune_history": "unknown",
    "known_genetic_findings": "unknown",
}

# Invented values, not a real person.
FULL_PROFILE = {
    "smoking_status": "current",
    "height_cm": 165,
    "weight_kg": 95.5,
    "activity_minutes_per_week": 0,
    "raised_lipids": "yes",
    "pregnancy_status": "yes",
    "family_diabetes": "yes",
    "family_heart_disease": "yes",
    "family_breast_cancer": "yes",
    "family_colorectal_cancer": "no",
}


def error_fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [error["loc"][-1] for error in response.json()["detail"]]


@pytest.fixture
def url(patient) -> str:
    return f"/patients/{patient['id']}/risk-profile"


# Reading


def test_a_patient_without_a_profile_reads_as_entirely_unknown(client, patient, url):
    response = client.get(url)

    assert response.status_code == 200
    assert response.json() == UNKNOWN_PROFILE | {"patient_id": patient["id"]}


@pytest.mark.parametrize("method", ["get", "post", "patch"])
def test_a_missing_patient_returns_404(client, method):
    response = client.request(method, "/patients/999/risk-profile", json={} if method != "get" else None)

    assert response.status_code == 404
    assert "Patient 999" in response.json()["detail"]


# Creating


def test_create_stores_every_factor_and_calculates_bmi(client, patient, url):
    response = client.post(url, json=FULL_PROFILE)

    assert response.status_code == 201
    body = response.json()
    assert body == UNKNOWN_PROFILE | FULL_PROFILE | {"patient_id": patient["id"], "stored": True, "bmi": 35.1, "height_cm": 165.0}
    assert client.get(url).json() == body


def test_an_empty_create_keeps_everything_unknown(client, patient, url):
    body = client.post(url, json={}).json()

    assert body == UNKNOWN_PROFILE | {"patient_id": patient["id"], "stored": True}
    assert "no" not in body.values()


def test_bmi_needs_both_measurements(client, url):
    assert client.post(url, json={"height_cm": 170}).json()["bmi"] is None


def test_a_second_create_returns_409(client, url):
    client.post(url, json={"smoking_status": "never"})

    response = client.post(url, json={"smoking_status": "current"})

    assert response.status_code == 409
    assert client.get(url).json()["smoking_status"] == "never"


def test_bmi_is_never_stored(client, url):
    client.post(url, json={"height_cm": 170, "weight_kg": 70})

    with Session(client.app.state.engine) as session:
        columns = [row[1] for row in session.connection().exec_driver_sql("PRAGMA table_info(patientriskprofile)").all()]

    assert "bmi" not in columns
    assert "height_cm" in columns


# Updating


def test_update_before_create_returns_404(client, url):
    response = client.patch(url, json={"smoking_status": "never"})

    assert response.status_code == 404
    assert "no risk profile" in response.json()["detail"]


def test_patch_leaves_omitted_fields_unchanged(client, url):
    created = client.post(url, json=FULL_PROFILE).json()

    response = client.patch(url, json={"smoking_status": "former"})

    assert response.status_code == 200
    assert response.json() == created | {"smoking_status": "former"}


def test_patch_null_clears_a_measurement_and_its_bmi(client, url):
    client.post(url, json={"height_cm": 170, "weight_kg": 70})

    body = client.patch(url, json={"weight_kg": None}).json()

    assert body["weight_kg"] is None
    assert body["bmi"] is None
    assert body["height_cm"] == 170


@pytest.mark.parametrize("field", ["smoking_status", "raised_lipids", "pregnancy_status", "family_diabetes"])
def test_patch_rejects_null_for_fields_that_have_unknown(client, url, field):
    client.post(url, json={})

    assert error_fields(client.patch(url, json={field: None})) == [field]


# Validation


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"height_cm": 49}, "height_cm"),
        ({"height_cm": 251}, "height_cm"),
        ({"height_cm": "170"}, "height_cm"),
        ({"height_cm": True}, "height_cm"),
        ({"weight_kg": 1}, "weight_kg"),
        ({"weight_kg": 351}, "weight_kg"),
        ({"activity_minutes_per_week": -1}, "activity_minutes_per_week"),
        ({"activity_minutes_per_week": 10081}, "activity_minutes_per_week"),
        ({"activity_minutes_per_week": 150.5}, "activity_minutes_per_week"),
        ({"smoking_status": "sometimes"}, "smoking_status"),
        ({"family_diabetes": "maybe"}, "family_diabetes"),
        ({"raised_lipids": False}, "raised_lipids"),
        ({"known_kidney_disease": "yes"}, "known_kidney_disease"),
        ({"bmi": 22}, "bmi"),
    ],
)
def test_create_rejects_invalid_values(client, url, body, field):
    assert error_fields(client.post(url, json=body)) == [field]
    assert client.get(url).json()["stored"] is False


def test_boundary_values_are_accepted(client, url):
    body = {"height_cm": 50, "weight_kg": 350, "activity_minutes_per_week": 10080}

    assert client.post(url, json=body).status_code == 201


@pytest.mark.parametrize(("sex", "accepted"), [("male", False), ("female", True), ("unknown", True)])
def test_pregnancy_yes_must_match_the_recorded_sex(client, sex, accepted):
    patient = client.post("/patients", json={"sex": sex}).json()

    response = client.post(f"/patients/{patient['id']}/risk-profile", json={"pregnancy_status": "yes"})

    if accepted:
        assert response.status_code == 201
    else:
        assert error_fields(response) == ["pregnancy_status"]


def test_male_patient_may_record_pregnancy_as_no_or_unknown(client):
    patient = client.post("/patients", json={"sex": "male"}).json()

    assert client.post(f"/patients/{patient['id']}/risk-profile", json={"pregnancy_status": "no"}).status_code == 201


def test_sex_cannot_change_to_male_while_pregnancy_is_yes(client, patient, url):
    client.post(url, json={"pregnancy_status": "yes"})
    patient_url = f"/patients/{patient['id']}"

    assert error_fields(client.patch(patient_url, json={"sex": "male"})) == ["sex"]
    client.patch(url, json={"pregnancy_status": "unknown"})
    assert client.patch(patient_url, json={"sex": "male"}).status_code == 200


def test_patch_is_judged_against_the_stored_sex(client):
    patient = client.post("/patients", json={"sex": "male"}).json()
    url = f"/patients/{patient['id']}/risk-profile"
    client.post(url, json={})

    assert error_fields(client.patch(url, json={"pregnancy_status": "yes"})) == ["pregnancy_status"]


# Screening safety


@pytest.fixture
def hypertensive_patient(client) -> dict:
    body = {
        "date_of_birth": "1985-03-15",
        "sex": "female",
        "diabetes_status": "diagnosed",
        "diabetes_type": "type_2",
        "diabetes_diagnosis_date": "2020-06-01",
        "hypertension_status": "diagnosed",
    }
    return client.post("/patients", json=body).json()


@pytest.mark.parametrize("endpoint", ["screening-preview", "screening-summary"])
def test_risk_factors_never_change_screening(client, hypertensive_patient, endpoint):
    base = f"/patients/{hypertensive_patient['id']}"
    client.post(f"{base}/medications", json={"medication_id": "lisinopril", "dose_text": "20 mg"})

    def statuses():
        body = client.get(f"{base}/{endpoint}").json()
        rules = body["actions"] if endpoint == "screening-preview" else [rule for test in body["tests"] for rule in test["rules"]]
        return {rule["rule_id"]: (rule["status"], rule["reasons"]) for rule in rules}, body["risk_factors"]

    before, facts_before = statuses()
    client.post(f"{base}/risk-profile", json=FULL_PROFILE)
    with_profile, facts = statuses()
    client.patch(f"{base}/risk-profile", json={"smoking_status": "never", "pregnancy_status": "no", "weight_kg": 60})
    after_change, _ = statuses()

    assert with_profile == before
    assert after_change == before
    # The facts are passed to the engine and reported, but none is actionable.
    assert all(fact["state"] == "unknown" for fact in facts_before)
    by_field = {fact["field"]: fact for fact in facts}
    assert by_field["smoking_status"]["state"] == "present"
    assert by_field["family_colorectal_cancer"]["state"] == "absent"
    assert by_field["bmi"]["state"] == "value"
    assert not any(fact["actionable"] for fact in facts)


@pytest.mark.parametrize("pregnancy", ["yes", "no", "unknown"])
def test_recorded_pregnancy_does_not_activate_pregnancy_eligibility(client, hypertensive_patient, pregnancy):
    base = f"/patients/{hypertensive_patient['id']}"
    client.post(f"{base}/risk-profile", json={"pregnancy_status": pregnancy})

    actions = {action["rule_id"]: action for action in client.get(f"{base}/screening-preview").json()["actions"]}
    missing = {item["field"]: item for item in actions["HTN03"]["missing_inputs"]}

    assert actions["HTN03"]["status"] == "needs_information"
    # VITALA records pregnancy, so it is never "not_collected". A stored value is
    # reported as recorded but not used until mapping RM01 is approved.
    reason = "unknown" if pregnancy == "unknown" else "recorded_pending_review"
    assert missing["pregnancy_status"] == {"field": "pregnancy_status", "reason": reason, "affects_eligibility": True}


@pytest.mark.parametrize("module", ["screening.py", "criteria.py", "history_mappings.py", "rules.py", "screening_tests.py"])
def test_the_screening_engine_reads_risk_factors_only_through_the_risk_context(module):
    # The engine receives a RiskContext (risk_inputs.py); it never queries the table itself.
    source = (BACKEND_DIR / "app" / module).read_text(encoding="utf-8")

    assert "PatientRiskProfile" not in source
    assert "risk_profile" not in source


# Existing databases


def test_existing_database_without_the_risk_table_keeps_its_records(settings):
    with TestClient(create_app(settings)) as first_run:
        patient = first_run.post("/patients", json={"sex": "female"}).json()
        first_run.post(f"/patients/{patient['id']}/medications", json={"medication_id": "metformin", "dose_text": "500 mg"})
        with Session(first_run.app.state.engine) as session:
            session.connection().exec_driver_sql("DROP TABLE patientriskprofile")
            session.commit()

    with TestClient(create_app(settings)) as second_run:
        assert second_run.get(f"/patients/{patient['id']}").json() == patient
        assert second_run.get(f"/patients/{patient['id']}/medications").json()[0]["medication_id"] == "metformin"
        assert second_run.get(f"/patients/{patient['id']}/risk-profile").json()["stored"] is False
        assert second_run.post(f"/patients/{patient['id']}/risk-profile", json={"smoking_status": "never"}).status_code == 201
