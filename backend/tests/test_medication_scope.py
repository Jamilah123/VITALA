"""Medication scope since 2026-11-14: metformin and ACE inhibitors only.

Archived catalogue entries stay readable, recorded uses are untouched, and
their rules are kept for reference but never evaluated.
"""

import json
import shutil

import pytest
from sqlmodel import Session, select

from app.catalogue import load_catalogue
from app.models import MedicationUse
from app.proposals import load_proposals
from app.rules import DATA_DIR, load_rule_set
from tests.scope_helpers import real_rule_set

ACTIVE = {"metformin", "enalapril", "lisinopril"}
ARCHIVED = {"losartan", "valsartan", "hydrochlorothiazide", "atorvastatin", "rosuvastatin", "warfarin", "methotrexate"}
ARCHIVED_RULES = {f"MED{n:02d}" for n in range(6, 15)}


def insert_historical_use(client, patient_id, medication_id, dose="historical dose"):
    """A use recorded before the scope change. The API no longer accepts new ones."""
    with Session(client.app.state.engine) as session:
        use = MedicationUse(patient_id=patient_id, medication_id=medication_id, dose_text=dose)
        session.add(use)
        session.commit()
        session.refresh(use)
        return use.id


def test_catalogue_keeps_every_entry_with_its_status(client):
    catalogue = {item["id"]: item for item in client.get("/medications").json()}
    assert set(catalogue) == ACTIVE | ARCHIVED
    assert {k for k, v in catalogue.items() if v["status"] == "active"} == ACTIVE
    assert {v["demo_scope"] for k, v in catalogue.items() if k in ACTIVE} == {"metformin", "ace_inhibitor"}
    for medication_id in ARCHIVED:
        entry = client.get(f"/medications/{medication_id}").json()
        assert entry["status"] == "archived" and entry["archived_on"] == "2026-11-14"
        # Identity is unchanged: nothing was reclassified.
        assert entry["drug_class"] in {"arb", "thiazide_diuretic", "statin", "vitamin_k_antagonist", "csdmard"}


@pytest.mark.parametrize("medication_id", sorted(ARCHIVED))
def test_new_uses_of_archived_medications_are_refused(client, patient, medication_id):
    response = client.post(f"/patients/{patient['id']}/medications", json={"medication_id": medication_id, "dose_text": "x"})
    assert response.status_code == 422
    assert "archived" in response.json()["detail"][0]["msg"]
    assert client.get(f"/patients/{patient['id']}/medications").json() == []


@pytest.mark.parametrize("medication_id", sorted(ACTIVE))
def test_in_scope_medications_can_be_added(client, patient, medication_id):
    assert client.post(f"/patients/{patient['id']}/medications", json={"medication_id": medication_id, "dose_text": "x"}).status_code == 201


def test_historical_uses_of_archived_medications_are_preserved_and_editable(client, patient):
    use_id = insert_historical_use(client, patient["id"], "warfarin")
    uses = client.get(f"/patients/{patient['id']}/medications").json()
    assert [(u["id"], u["medication_id"], u["dose_text"]) for u in uses] == [(use_id, "warfarin", "historical dose")]

    updated = client.patch(f"/patients/{patient['id']}/medications/{use_id}", json={"dose_text": "5 mg"})
    assert updated.status_code == 200 and updated.json()["medication_id"] == "warfarin"
    assert client.delete(f"/patients/{patient['id']}/medications/{use_id}").status_code == 204


def test_archived_medications_never_trigger_rules(client, patient):
    for medication_id in ("losartan", "hydrochlorothiazide", "atorvastatin", "warfarin", "methotrexate"):
        insert_historical_use(client, patient["id"], medication_id)

    preview = client.get(f"/patients/{patient['id']}/screening-preview").json()
    actions = {a["rule_id"]: a for a in preview["actions"]}
    assert not set(actions) & ARCHIVED_RULES
    # MED03/MED04 still name losartan and hydrochlorothiazide, but those are archived now.
    assert {actions[r]["status"] for r in ("MED03", "MED04", "MED05")} == {"not_triggered"}
    assert not any(a["status"] == "candidate" and a["track"] == "medication" for a in actions.values())
    assert sorted(m["medication_id"] for m in preview["out_of_scope_medications"]) == sorted(
        ["losartan", "hydrochlorothiazide", "atorvastatin", "warfarin", "methotrexate"]
    )


def test_ace_inhibitors_still_trigger_their_rules(client, patient):
    client.post(f"/patients/{patient['id']}/medications", json={"medication_id": "lisinopril", "dose_text": "10 mg"})
    actions = {a["rule_id"]: a for a in client.get(f"/patients/{patient['id']}/screening-preview").json()["actions"]}
    # The patient fixture has diagnosed type 2 diabetes.
    assert actions["MED04"]["matched_medication_ids"] == ["lisinopril"]
    assert actions["MED04"]["status"] in {"candidate", "needs_information"}
    assert actions["MED05"]["status"] == "not_applicable"
    assert actions["MED04"]["auto_schedule_enabled"] is False
    assert "C06" in actions["MED04"]["conflict_ids"]


def test_summary_keeps_archived_tests_and_their_records(client, patient):
    client.post(
        f"/patients/{patient['id']}/screening-records",
        json={"test_id": "inr", "test_name": "INR", "completed_on": "2026-01-05", "result": "2.4", "source": "lab_report"},
    )
    tests = {t["test_id"]: t for t in client.get(f"/patients/{patient['id']}/screening-summary").json()["tests"]}
    assert tests["inr"]["rules"] == []
    assert tests["inr"]["archived_rule_ids"] == ["MED11", "MED12", "MED13"]
    assert [r["result"] for r in tests["inr"]["recorded_tests"]] == ["2.4"]
    assert tests["lipid_profile"]["archived_rule_ids"] == ["MED07", "MED08"]
    assert [r["rule_id"] for r in tests["lipid_profile"]["rules"]] == ["HTN06"]


def test_scope_endpoint_and_proposals(client):
    scope = client.get("/medication-scope").json()
    assert set(scope["active_medication_ids"]) == ACTIVE
    assert set(scope["archived_rule_ids"]) == ARCHIVED_RULES
    assert scope["active_rule_ids"] == ["MED01", "MED02", "MED03", "MED04", "MED05"]

    proposals = client.get("/medication-rule-proposals").json()
    assert [p["id"] for p in proposals] == scope["proposal_ids"] == ["MRP01", "MRP02", "MRP03", "MRP04", "MRP05", "MRP06"]
    assert all(p["executable"] is False and p["auto_schedule_enabled"] is False and p["reviewer"] is None for p in proposals)
    assert {p["review_status"] for p in proposals} == {"pending_clinical_review", "not_suitable_for_rule"}
    sources = {t["source_id"] for p in proposals for t in p["timing_as_stated"]}
    assert sources <= {"S10", "S11", "S12"}


def test_proposals_never_reach_the_engine(client, patient):
    rule_ids = {a["rule_id"] for a in client.get(f"/patients/{patient['id']}/screening-preview").json()["actions"]}
    assert not any(rule_id.startswith("MRP") for rule_id in rule_ids)
    # No executable rule cites the PDF corpus.
    assert all(source.source_id not in {"S10", "S11", "S12"} for rule in real_rule_set().rules for source in rule.evidence)


def _copy_data(tmp_path):
    for path in DATA_DIR.glob("*.json"):
        shutil.copy(path, tmp_path / path.name)
    return tmp_path


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p: p[0].update(executable=True), "executable"),
        (lambda p: p[0].update(auto_schedule_enabled=True), "auto_schedule_enabled"),
        (lambda p: p[0].update(reviewer="Someone"), "reviewer"),
        (lambda p: p[0].update(drug_ids=["warfarin"]), "not an active catalogue medication"),
        (lambda p: p[0]["timing_as_stated"][0].update(source_id="S99"), "S99"),
        (lambda p: p[0].update(related_rule_ids=["MED99"]), "MED99"),
        (lambda p: p[0]["inputs_not_collected"].pop(), "listed once"),
    ],
)
def test_invalid_proposals_stop_startup(tmp_path, change, message):
    data = _copy_data(tmp_path)
    proposals = json.loads((data / "medication_rule_proposals.json").read_text(encoding="utf-8"))
    change(proposals)
    (data / "medication_rule_proposals.json").write_text(json.dumps(proposals), encoding="utf-8")
    catalogue = load_catalogue(DATA_DIR / "medications.json")
    with pytest.raises(ValueError, match=message):
        load_proposals(load_rule_set(catalogue), catalogue, data / "medication_rule_proposals.json")


def test_a_rule_cannot_stay_active_when_all_its_medications_are_archived(tmp_path):
    data = _copy_data(tmp_path)
    rules = json.loads((data / "medication_monitoring.json").read_text(encoding="utf-8"))
    rules[10].update(lifecycle="active", archived_on=None, archive_reason_ar=None)  # MED11, warfarin only
    (data / "medication_monitoring.json").write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="MED11"):
        load_rule_set(load_catalogue(data / "medications.json"), data)


def test_an_archived_catalogue_entry_needs_a_date_and_reason(tmp_path):
    data = _copy_data(tmp_path)
    meds = json.loads((data / "medications.json").read_text(encoding="utf-8"))
    next(m for m in meds if m["id"] == "warfarin")["archived_on"] = None
    (data / "medications.json").write_text(json.dumps(meds, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="warfarin"):
        load_catalogue(data / "medications.json")


def test_existing_patient_medication_records_are_never_rewritten_by_startup(settings, client, patient):
    use_id = insert_historical_use(client, patient["id"], "losartan", "50 mg")
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as restarted:
        with Session(restarted.app.state.engine) as session:
            stored = session.exec(select(MedicationUse).where(MedicationUse.id == use_id)).one()
            assert (stored.medication_id, stored.dose_text) == ("losartan", "50 mg")
        assert restarted.get(f"/medications/losartan").json()["generic_name"] == "Losartan"
