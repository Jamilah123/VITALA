"""Allergies, structured family history and genetic findings."""

import pytest

from tests.conftest import seed_all


def fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [error["loc"][-1] for error in response.json()["detail"]]


@pytest.fixture
def base(patient) -> str:
    return f"/patients/{patient['id']}"


# ---------------------------------------------------------------- allergies


def test_allergy_records_keep_reaction_severity_and_source(client, base):
    created = client.post(f"{base}/allergies", json={"allergen": "Penicillin", "category": "drug", "reaction": "Hives", "severity": "moderate", "verification": "patient_reported"})
    assert created.status_code == 201
    body = created.json()
    assert (body["allergen"], body["reaction"], body["severity"], body["verification"]) == ("Penicillin", "Hives", "moderate", "patient_reported")
    minimal = client.post(f"{base}/allergies", json={"allergen": "Peanuts"}).json()
    # Nothing is assumed: an allergy without details stays unknown.
    assert (minimal["category"], minimal["severity"], minimal["verification"], minimal["reaction"]) == ("unknown", "unknown", "unknown", None)
    assert [a["allergen"] for a in client.get(f"{base}/allergies").json()] == ["Penicillin", "Peanuts"]


def test_the_same_allergen_is_not_stored_twice(client, base):
    client.post(f"{base}/allergies", json={"allergen": "Penicillin"})
    assert client.post(f"{base}/allergies", json={"allergen": "  penicillin "}).status_code == 409


def test_confirmed_no_allergies_cannot_coexist_with_records(client, base):
    client.post(f"{base}/risk-profile", json={"known_allergies": "no"})
    assert fields(client.post(f"{base}/allergies", json={"allergen": "Latex"})) == ["known_allergies"]
    client.patch(f"{base}/risk-profile", json={"known_allergies": "unknown"})
    client.post(f"{base}/allergies", json={"allergen": "Latex"})
    assert fields(client.patch(f"{base}/risk-profile", json={"known_allergies": "no"})) == ["known_allergies"]


def test_allergy_update_and_delete(client, base):
    allergy = client.post(f"{base}/allergies", json={"allergen": "Sulfa"}).json()
    updated = client.patch(f"{base}/allergies/{allergy['id']}", json={"severity": "severe", "verification": "clinically_confirmed"}).json()
    assert (updated["severity"], updated["verification"]) == ("severe", "clinically_confirmed")
    assert client.delete(f"{base}/allergies/{allergy['id']}").status_code == 204
    assert client.get(f"{base}/allergies").json() == []


def test_allergies_never_change_screening(client, base):
    before = client.get(f"{base}/screening-preview").json()["actions"]
    client.post(f"{base}/allergies", json={"allergen": "Metformin", "category": "drug", "severity": "severe"})
    assert client.get(f"{base}/screening-preview").json()["actions"] == before


# ---------------------------------------------------------------- family history


def test_relatives_with_several_conditions_are_counted_once(client, base):
    mother = client.post(
        f"{base}/family-history/relatives",
        json={
            "relationship": "mother",
            "conditions": [
                {"category": "cancer", "condition": "breast", "age_at_diagnosis": 62, "verification": "patient_reported"},
                {"category": "cancer", "condition": "ovarian"},
                {"category": "chronic", "condition": "type_2_diabetes"},
            ],
        },
    )
    assert mother.status_code == 201
    assert mother.json()["degree"] == "first" and len(mother.json()["conditions"]) == 3
    client.post(f"{base}/family-history/relatives", json={"relationship": "sister", "label": "older sister", "conditions": [{"category": "cancer", "condition": "breast"}]})
    client.post(f"{base}/family-history/relatives", json={"relationship": "sister", "label": "younger sister"})
    client.post(f"{base}/family-history/relatives", json={"relationship": "paternal_aunt", "conditions": [{"category": "autoimmune", "condition": "systemic_lupus"}]})

    history = client.get(f"{base}/medical-history").json()
    assert history["family_counts"] == {"relatives_with_cancer": 2, "first_degree_relatives_with_cancer": 2, "relatives_with_chronic_or_autoimmune": 2}
    assert [r["label"] for r in history["family_relatives"] if r["relationship"] == "sister"] == ["older sister", "younger sister"]
    facts = {f["field"]: f for f in history["risk_factors"]}
    assert facts["family_cancer_history"]["state"] == "present" and facts["family_cancer_history"]["detail"]["affected_relatives"] == 2
    assert not any(f["actionable"] for f in history["risk_factors"])


@pytest.mark.parametrize(
    ("condition", "error"),
    [
        ({"category": "cancer", "condition": "type_2_diabetes"}, "condition"),
        ({"category": "cancer", "condition": "other"}, "condition_other"),
        ({"category": "chronic", "condition": "asthma", "condition_other": "x"}, "condition_other"),
        ({"category": "cancer", "condition": "breast", "age_at_diagnosis": 130}, "age_at_diagnosis"),
        ({"category": "genetic", "condition": "breast"}, "category"),
    ],
)
def test_conditions_use_the_vocabulary(client, base, condition, error):
    relative = client.post(f"{base}/family-history/relatives", json={"relationship": "father"}).json()
    assert error in fields(client.post(f"{base}/family-history/relatives/{relative['id']}/conditions", json=condition))


def test_other_condition_needs_its_description(client, base):
    relative = client.post(f"{base}/family-history/relatives", json={"relationship": "brother"}).json()
    created = client.post(f"{base}/family-history/relatives/{relative['id']}/conditions", json={"category": "cancer", "condition": "other", "condition_other": "Sarcoma"})
    assert created.status_code == 201 and created.json()["condition_other"] == "Sarcoma"


def test_duplicate_condition_for_the_same_relative_is_refused(client, base):
    relative = client.post(f"{base}/family-history/relatives", json={"relationship": "father"}).json()
    url = f"{base}/family-history/relatives/{relative['id']}/conditions"
    client.post(url, json={"category": "chronic", "condition": "hypertension"})
    assert client.post(url, json={"category": "chronic", "condition": "hypertension"}).status_code == 409


def test_a_confirmed_no_flag_blocks_contradicting_records_both_ways(client, base):
    client.post(f"{base}/risk-profile", json={"family_breast_cancer": "no"})
    response = client.post(f"{base}/family-history/relatives", json={"relationship": "mother", "conditions": [{"category": "cancer", "condition": "breast"}]})
    assert set(fields(response)) == {"family_breast_cancer"}
    # The failed request created nothing.
    assert client.get(f"{base}/family-history").json() == []
    # A different cancer is fine.
    assert client.post(f"{base}/family-history/relatives", json={"relationship": "mother", "conditions": [{"category": "cancer", "condition": "lung"}]}).status_code == 201
    assert "family_cancer_history" in fields(client.patch(f"{base}/risk-profile", json={"family_cancer_history": "no"}))


def test_unknown_flags_get_a_note_and_are_never_changed(client, base):
    client.post(f"{base}/family-history/relatives", json={"relationship": "father", "conditions": [{"category": "chronic", "condition": "type_2_diabetes"}]})
    history = client.get(f"{base}/medical-history").json()
    assert history["risk_profile"]["family_diabetes"] == "unknown"
    assert {n["field"] for n in history["consistency_notes"]} >= {"family_diabetes", "family_chronic_or_autoimmune_history"}


def test_deleting_a_relative_removes_their_conditions(client, base):
    relative = client.post(f"{base}/family-history/relatives", json={"relationship": "mother", "conditions": [{"category": "cancer", "condition": "breast"}]}).json()
    assert client.delete(f"{base}/family-history/relatives/{relative['id']}").status_code == 204
    assert client.get(f"{base}/medical-history").json()["family_counts"]["relatives_with_cancer"] == 0


def test_condition_update_and_delete(client, base):
    relative = client.post(f"{base}/family-history/relatives", json={"relationship": "mother", "conditions": [{"category": "cancer", "condition": "breast"}]}).json()
    condition_id = relative["conditions"][0]["id"]
    updated = client.patch(f"{base}/family-history/conditions/{condition_id}", json={"age_at_diagnosis": 50, "verification": "clinically_confirmed"}).json()
    assert (updated["age_at_diagnosis"], updated["verification"]) == (50, "clinically_confirmed")
    assert client.delete(f"{base}/family-history/conditions/{condition_id}").status_code == 204


def test_family_history_never_changes_screening(client, base):
    before = client.get(f"{base}/screening-summary").json()["tests"]
    client.post(f"{base}/family-history/relatives", json={"relationship": "mother", "conditions": [{"category": "cancer", "condition": "breast"}, {"category": "chronic", "condition": "type_2_diabetes"}]})
    after = client.get(f"{base}/screening-summary").json()["tests"]
    assert after == before


# ---------------------------------------------------------------- genetic findings


def test_genetic_findings_are_not_assumed_confirmed_and_change_nothing(client, base):
    before = client.get(f"{base}/screening-preview").json()["actions"]
    finding = client.post(f"{base}/genetic-findings", json={"name": "BRCA1 pathogenic variant", "gene": "BRCA1"}).json()
    assert finding["verification"] == "unknown"
    assert client.get(f"{base}/screening-preview").json()["actions"] == before
    confirmed = client.patch(f"{base}/genetic-findings/{finding['id']}", json={"verification": "clinically_confirmed", "test_source": "Synthetic lab report"}).json()
    assert confirmed["verification"] == "clinically_confirmed"
    assert client.get(f"{base}/screening-preview").json()["actions"] == before


def test_genetic_finding_dates_are_checked(client, base):
    assert fields(client.post(f"{base}/genetic-findings", json={"name": "X", "test_date": "2999-01-01"})) == ["test_date"]
    assert fields(client.post(f"{base}/genetic-findings", json={"name": "X", "test_date": "1980-01-01"})) == ["test_date"]


def test_confirmed_no_genetic_findings_blocks_new_findings(client, base):
    client.post(f"{base}/risk-profile", json={"known_genetic_findings": "no"})
    assert fields(client.post(f"{base}/genetic-findings", json={"name": "Lynch syndrome"})) == ["known_genetic_findings"]


# ---------------------------------------------------------------- isolation and summaries


def test_one_patient_cannot_reach_another_patients_records(client, base, patient):
    other = client.post("/patients", json={"sex": "male"}).json()
    allergy = client.post(f"{base}/allergies", json={"allergen": "Penicillin"}).json()
    relative = client.post(f"{base}/family-history/relatives", json={"relationship": "mother", "conditions": [{"category": "cancer", "condition": "breast"}]}).json()
    finding = client.post(f"{base}/genetic-findings", json={"name": "X"}).json()
    other_base = f"/patients/{other['id']}"
    assert client.patch(f"{other_base}/allergies/{allergy['id']}", json={"severity": "mild"}).status_code == 404
    assert client.delete(f"{other_base}/family-history/relatives/{relative['id']}").status_code == 404
    assert client.patch(f"{other_base}/family-history/conditions/{relative['conditions'][0]['id']}", json={"age_at_diagnosis": 1}).status_code == 404
    assert client.post(f"{other_base}/family-history/relatives/{relative['id']}/conditions", json={"category": "cancer", "condition": "lung"}).status_code == 404
    assert client.delete(f"{other_base}/genetic-findings/{finding['id']}").status_code == 404
    assert client.get(f"{other_base}/medical-history").json()["allergies"] == []


def test_missing_patient_returns_404(client):
    for path in ("medical-history", "allergies", "family-history", "genetic-findings"):
        assert client.get(f"/patients/999/{path}").status_code == 404


def test_vocabulary_endpoint(client):
    vocabulary = client.get("/medical-history/vocabulary").json()
    assert "breast" in vocabulary["conditions"]["cancer"] and "systemic_lupus" in vocabulary["conditions"]["autoimmune"]
    assert "maternal_grandmother" in vocabulary["relationships"]
    assert vocabulary["verification"] == ["patient_reported", "clinically_confirmed", "unknown"]


def test_clinician_summary_shows_the_new_history(client):
    ids = seed_all(client)
    appointments = client.get(f"/clinics/{ids['clinic_id']}/appointments").json()
    links = {p["id"]: p["patient"]["id"] for p in client.get(f"/clinics/{ids['clinic_id']}/patients").json()}
    virtual = next(a for a in appointments if links[a["clinic_patient_id"]] == ids["history_patient_id"])
    summary = client.get(f"/clinics/{ids['clinic_id']}/appointments/{virtual['id']}/summary").json()

    history = summary["medical_history"]
    assert [a["allergen"] for a in history["allergies"]] == ["Penicillin"]
    assert history["family_counts"]["relatives_with_cancer"] == 2
    assert {r["relationship"] for r in history["family_relatives"]} == {"mother", "sister"}
    assert history["genetic_findings"] == []
    assert history["risk_profile"]["known_genetic_findings"] == "unknown"
    facts = {f["field"]: f for f in history["risk_factors"]}
    assert facts["smoking_status"]["state"] == "present" and facts["smoking_status"]["source"] == "patient_reported"
    assert history["screening_uses_risk_factors"] is False
    assert summary["insurance"] == {"coverage_status": "unknown", "insurer_name": None, "insurance_class": None, "eligibility_verified": False}
    assert {m["medication_id"] for m in summary["medications"]} == {"metformin", "lisinopril"}
    assert summary["clinically_validated"] is False
