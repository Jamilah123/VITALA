from datetime import date

import pytest

from tests.scope_helpers import full_scope_rule_set

from app.catalogue import load_catalogue
from app.models import ConditionStatus, DiabetesType, MedicationUse, Patient
from app.rules import DATA_DIR
from app.criteria import CRITERIA
from app.screening import preview_screening

TODAY = date(2026, 11, 4)
DIAGNOSED = ConditionStatus.diagnosed
NOT_DIAGNOSED = ConditionStatus.not_diagnosed
UNKNOWN = ConditionStatus.unknown

# Invented values, not a real person.
TYPE_2_DIABETES = {
    "date_of_birth": date(1985, 3, 15),
    "sex": "female",
    "diabetes_status": DIAGNOSED,
    "diabetes_type": DiabetesType.type_2,
    "diabetes_diagnosis_date": date(2020, 6, 1),
}


@pytest.fixture(scope="module")
def rule_set():
    # Engine mechanics are tested on every rule; the scope change has its own tests.
    return full_scope_rule_set()


def use(medication_id, start_date=None):
    return MedicationUse(patient_id=1, medication_id=medication_id, dose_text="synthetic", start_date=start_date)


def evaluate(rule_set, uses=(), **profile):
    preview = preview_screening(rule_set, Patient(id=1, **profile), list(uses), TODAY)
    return {action.rule_id: action for action in preview.actions}


def missing(action):
    return {item.field: (item.reason, item.affects_eligibility) for item in action.missing_inputs}


def statuses(actions, prefix):
    return {rule_id: action.status for rule_id, action in actions.items() if rule_id.startswith(prefix)}


# Known conditions


def test_known_condition_makes_matching_rules_candidates(rule_set):
    actions = evaluate(rule_set, **TYPE_2_DIABETES)

    for rule_id in ["DM03", "DM04", "DM05", "DM08", "DM09", "DM10"]:
        assert actions[rule_id].status == "candidate", rule_id
    assert actions["DM06"].status == "not_applicable"
    assert actions["DM06"].reasons == ["diabetes_type_not_covered"]


@pytest.mark.parametrize(
    ("diagnosed_on", "status", "reasons"),
    [
        (date(2021, 11, 4), "candidate", []),
        (date(2021, 11, 5), "not_applicable", ["diabetes_duration_below_minimum"]),
        (date(2025, 1, 1), "not_applicable", ["diabetes_duration_below_minimum"]),
    ],
)
def test_type_1_kidney_rules_follow_the_five_year_threshold(rule_set, diagnosed_on, status, reasons):
    actions = evaluate(rule_set, diabetes_status=DIAGNOSED, diabetes_type=DiabetesType.type_1, diabetes_diagnosis_date=diagnosed_on)

    for rule_id in ["DM03", "DM04"]:
        assert actions[rule_id].status == status
        assert actions[rule_id].reasons == reasons


def test_age_criterion_uses_the_date_of_birth(rule_set):
    child = evaluate(rule_set, date_of_birth=date(2012, 1, 1), hypertension_status=DIAGNOSED)
    no_birth_date = evaluate(rule_set, hypertension_status=DIAGNOSED)

    assert child["HTN03"].status == "not_applicable"
    assert child["HTN03"].reasons == ["age_below_minimum"]
    assert missing(no_birth_date["HTN03"])["date_of_birth"] == ("unknown", True)


# Unknown conditions


def test_unknown_conditions_are_never_treated_as_negative(rule_set):
    actions = evaluate(rule_set)

    for rule_id, action in actions.items():
        if not rule_id.startswith("MED"):
            assert action.status == "needs_information", rule_id
            condition = "diabetes" if rule_id.startswith("DM") else "hypertension"
            assert missing(action)[f"{condition}_status"] == ("unknown", True)


def test_not_diagnosed_excludes_with_an_explicit_reason(rule_set):
    actions = evaluate(rule_set, diabetes_status=NOT_DIAGNOSED, hypertension_status=NOT_DIAGNOSED)

    for rule_id, action in actions.items():
        if not rule_id.startswith("MED"):
            assert action.status == "not_applicable", rule_id
            assert action.reasons in (["diabetes_not_diagnosed"], ["hypertension_not_diagnosed"])
            assert action.missing_inputs == []


def test_unknown_diabetes_type_leaves_type_specific_rules_undecided(rule_set):
    actions = evaluate(rule_set, diabetes_status=DIAGNOSED)

    for rule_id in ["DM03", "DM05", "DM06", "DM10"]:
        assert actions[rule_id].status == "needs_information"
        assert missing(actions[rule_id])["diabetes_type"] == ("unknown", True)
    assert actions["DM08"].status == "candidate"


def test_unknown_type_1_diagnosis_date_leaves_duration_rules_undecided(rule_set):
    actions = evaluate(rule_set, diabetes_status=DIAGNOSED, diabetes_type=DiabetesType.type_1)

    assert actions["DM03"].status == "needs_information"
    assert missing(actions["DM03"])["diabetes_diagnosis_date"] == ("unknown", True)


# Medication records


def test_recorded_medication_triggers_its_rules(rule_set):
    actions = evaluate(rule_set, [use("metformin", date(2021, 1, 10))], **TYPE_2_DIABETES)

    for rule_id in ["MED01", "MED02"]:
        assert actions[rule_id].status == "candidate"
        assert actions[rule_id].matched_medication_ids == ["metformin"]
    assert "medication_start_date" not in missing(actions["MED01"])


def test_unknown_medication_start_date_is_reported(rule_set):
    actions = evaluate(rule_set, [use("metformin")], **TYPE_2_DIABETES)

    assert missing(actions["MED01"])["medication_start_date"] == ("unknown", False)


def test_unrecorded_medications_are_not_triggered_rather_than_negative(rule_set):
    actions = evaluate(rule_set, **TYPE_2_DIABETES)

    for rule_id, action in actions.items():
        if rule_id.startswith("MED"):
            assert action.status == "not_triggered"
            assert action.reasons == ["no_matching_medication_recorded"]


@pytest.mark.parametrize(
    ("diabetes_status", "expected"),
    [
        (UNKNOWN, {"MED03": "needs_information", "MED04": "needs_information", "MED05": "needs_information"}),
        (DIAGNOSED, {"MED03": "candidate", "MED04": "candidate", "MED05": "not_applicable"}),
        (NOT_DIAGNOSED, {"MED03": "not_applicable", "MED04": "not_applicable", "MED05": "candidate"}),
    ],
)
def test_medication_rules_depend_on_the_diabetes_context(rule_set, diabetes_status, expected):
    actions = evaluate(rule_set, [use("losartan", date(2022, 1, 1))], diabetes_status=diabetes_status)

    assert {rule_id: actions[rule_id].status for rule_id in expected} == expected


def test_a_medication_never_implies_a_diagnosis(rule_set):
    actions = evaluate(rule_set, [use("metformin", date(2021, 1, 10))])

    assert set(statuses(actions, "DM").values()) == {"needs_information"}


def test_every_matching_medication_is_listed(rule_set):
    actions = evaluate(rule_set, [use("losartan"), use("hydrochlorothiazide")], diabetes_status=DIAGNOSED)

    assert actions["MED03"].matched_medication_ids == ["hydrochlorothiazide", "losartan"]
    assert actions["MED05"].matched_medication_ids == ["losartan"]


def test_methotrexate_rule_needs_its_indication(rule_set):
    actions = evaluate(rule_set, [use("methotrexate", date(2026, 1, 1))])

    assert actions["MED14"].status == "needs_information"
    assert missing(actions["MED14"])["medication_indication"] == ("not_collected", True)
    assert actions["MED14"].conflict_ids == ["C04"]


# Missing information


def test_inputs_vitala_does_not_record_are_reported_as_not_collected(rule_set):
    actions = evaluate(rule_set, **TYPE_2_DIABETES)

    assert actions["DM01"].status == "needs_information"
    assert missing(actions["DM01"]) == {
        "last_hba1c_date": ("not_collected", False),
        "hba1c_at_individual_target": ("not_collected", True),
    }


def test_each_missing_fact_is_reported_once_under_its_stored_name(rule_set):
    action = evaluate(rule_set)["HTN04"]
    fields = [item.field for item in action.missing_inputs]

    assert fields.count("hypertension_status") == 1
    assert "hypertension_diagnosed" not in fields


def test_rules_that_need_uncollected_data_are_never_candidates(rule_set):
    everything = [use(medication_id, date(2022, 1, 1)) for medication_id in load_catalogue(DATA_DIR / "medications.json")]
    actions = evaluate(rule_set, everything, hypertension_status=DIAGNOSED, **TYPE_2_DIABETES)

    for rule_id, criteria in CRITERIA.items():
        if (criteria.uncollected or criteria.on_record) and actions[rule_id].status != "not_applicable":
            assert actions[rule_id].status == "needs_information", rule_id


@pytest.mark.parametrize(
    "profile",
    [{}, TYPE_2_DIABETES, {"diabetes_status": DIAGNOSED}, {"hypertension_status": DIAGNOSED}],
)
def test_status_always_agrees_with_the_missing_inputs(rule_set, profile):
    actions = evaluate(rule_set, [use("losartan"), use("warfarin")], **profile)

    for action in actions.values():
        blocking = [item for item in action.missing_inputs if item.affects_eligibility]
        assert (action.status == "needs_information") == bool(blocking), action.rule_id


# Review status and sources


def test_every_action_is_an_unreviewed_draft_that_schedules_nothing(rule_set):
    preview = preview_screening(rule_set, Patient(id=1, **TYPE_2_DIABETES), [use("metformin")], TODAY)

    assert preview.clinically_approved is False
    assert preview.auto_schedule_enabled is False
    assert "لم يراجعها طبيب" in preview.notice_ar
    for action in preview.actions:
        assert action.review_status == "draft_not_clinician_reviewed"
        assert action.auto_schedule_enabled is False


def test_actions_cite_their_sources_and_conflicts(rule_set):
    actions = evaluate(rule_set, **TYPE_2_DIABETES)

    dm07 = actions["DM07"]
    assert [source.source_id for source in dm07.sources] == ["S07", "S01", "S02"]
    assert all(source.url.startswith("https://www.moh.gov.sa/") for source in dm07.sources)
    assert dm07.conflict_ids == ["C01"]
    assert actions["HTN01"].conflict_ids == ["C03"]
    assert actions["DM04"].sources[1].locator == "PDF p. 82"


# API


def test_preview_for_a_missing_patient_returns_404(client):
    assert client.get("/patients/999/screening-preview").status_code == 404


def test_preview_uses_the_stored_profile_and_medications(client, patient):
    client.post(f"/patients/{patient['id']}/medications", json={"medication_id": "metformin", "dose_text": "500 mg"})

    response = client.get(f"/patients/{patient['id']}/screening-preview")

    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == patient["id"]
    assert body["evaluated_on"] == date.today().isoformat()
    assert body["clinically_approved"] is False
    assert body["auto_schedule_enabled"] is False
    actions = {action["rule_id"]: action for action in body["actions"]}
    # Since 2026-11-14 the nine rules for archived medications are kept but not evaluated.
    archived = {f"MED{number:02d}" for number in range(6, 15)}
    assert set(actions) == set(CRITERIA) - archived
    assert actions["DM05"]["status"] == "candidate"
    assert actions["DM06"]["status"] == "not_applicable"
    assert actions["HTN01"]["status"] == "needs_information"
    assert actions["MED01"]["status"] == "candidate"
    assert actions["MED03"]["status"] == "not_triggered"
    assert "schedule" not in actions["DM01"]


def test_preview_follows_profile_updates(client, patient):
    url = f"/patients/{patient['id']}"
    client.patch(url, json={"hypertension_status": "not_diagnosed"})

    actions = client.get(f"{url}/screening-preview").json()["actions"]

    assert {action["status"] for action in actions if action["track"] == "hypertension"} == {"not_applicable"}
