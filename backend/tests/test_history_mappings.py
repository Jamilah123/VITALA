from dataclasses import replace
from datetime import date

import pytest

from tests.scope_helpers import full_scope_rule_set

from app.history_mappings import (
    AMBIGUOUS_HISTORY_FIELDS,
    CLINICAL_INTERPRETATIONS,
    HISTORY_MAPPINGS,
    AmbiguousHistoryField,
    HistoryMapping,
    changes_eligibility,
    check_history_mappings,
    mapped_rule_ids,
)
from app.models import ConditionStatus, DiabetesType, MedicationUse, Patient, RecordSource, ScreeningRecord
from app.screening import preview_screening, summarize_screening

TODAY = date(2026, 11, 4)
DIAGNOSED = ConditionStatus.diagnosed

# Invented values, not a real person.
PROFILE = {
    "date_of_birth": date(1985, 3, 15),
    "sex": "female",
    "diabetes_status": DIAGNOSED,
    "diabetes_type": DiabetesType.type_2,
    "diabetes_diagnosis_date": date(2020, 6, 1),
    "hypertension_status": DIAGNOSED,
}
MEDICATIONS = ["metformin", "losartan", "hydrochlorothiazide", "atorvastatin"]


@pytest.fixture(scope="module")
def rule_set():
    # Engine mechanics are tested on every rule; the scope change has its own tests.
    return full_scope_rule_set()


@pytest.fixture(scope="module")
def rules(rule_set):
    return {rule.id: rule for rule in rule_set.rules}


def approve(*mapping_ids):
    approved = set(mapping_ids) if mapping_ids else {mapping.id for mapping in HISTORY_MAPPINGS}
    return tuple(
        replace(mapping, status="approved", reviewer="Synthetic Reviewer", reviewed_on=date(2026, 11, 1))
        if mapping.id in approved
        else mapping
        for mapping in HISTORY_MAPPINGS
    )


def record(record_id, test_id, completed_on, result=None):
    return ScreeningRecord(
        id=record_id,
        patient_id=1,
        test_id=test_id,
        test_name=test_id,
        completed_on=completed_on,
        result=result,
        source=RecordSource.lab_report,
    )


def evaluate(rule_set, records=(), mappings=HISTORY_MAPPINGS, medications=MEDICATIONS):
    uses = [MedicationUse(patient_id=1, medication_id=medication_id, dose_text="synthetic") for medication_id in medications]
    preview = preview_screening(rule_set, Patient(id=1, **PROFILE), uses, TODAY, list(records), mappings)
    return {action.rule_id: action for action in preview.actions}


def summarize(rule_set, records=(), mappings=HISTORY_MAPPINGS):
    uses = [MedicationUse(patient_id=1, medication_id=medication_id, dose_text="synthetic") for medication_id in MEDICATIONS]
    summary = summarize_screening(rule_set, Patient(id=1, **PROFILE), uses, list(records), TODAY, mappings)
    return {test.test_id: test for test in summary.tests}


def missing(action):
    return {item.field: (item.reason, item.affects_eligibility) for item in action.missing_inputs}


EVERY_TEST_RECORDED = [record(index, test_id, date(2026, 1, 1)) for index, test_id in enumerate(
    ["hba1c", "uacr", "egfr", "eye_exam", "foot_exam", "neuropathy_exam", "bp_followup", "annual_htn_review", "electrolytes",
     "lipid_profile", "fasting_glucose", "urine_assessment", "ecg", "vitamin_b12", "renal_potassium", "thiazide_labs",
     "liver_enzymes", "ck", "inr", "cbc_lft_renal", "blood_pressure"],
    start=1,
)]


# The mapping table


def test_mapping_table_is_valid_and_entirely_pending_review(rules):
    check_history_mappings(rules.values())

    for mapping in HISTORY_MAPPINGS:
        assert mapping.status == "pending_review", mapping.id
        assert mapping.reviewer is None and mapping.reviewed_on is None
        assert mapping.version >= 1


def test_only_direct_facts_are_mapped_never_interpretations():
    assert {mapping.kind for mapping in HISTORY_MAPPINGS} <= {"completion_date", "test_on_record"}
    assert not {mapping.field for mapping in HISTORY_MAPPINGS} & CLINICAL_INTERPRETATIONS
    assert "hba1c_at_individual_target" in CLINICAL_INTERPRETATIONS


def test_only_the_eye_exam_date_mapping_changes_eligibility(rules):
    assert [mapping.id for mapping in HISTORY_MAPPINGS if changes_eligibility(mapping, rules)] == ["HM05"]


def test_a_mapping_reaches_only_the_rules_of_its_own_test(rules):
    by_id = {mapping.id: mapping for mapping in HISTORY_MAPPINGS}

    assert mapped_rule_ids(by_id["HM03"], rules) == ["DM04", "HTN04", "MED02"]
    assert mapped_rule_ids(by_id["HM08"], rules) == ["HTN01"]
    assert mapped_rule_ids(by_id["HM09"], rules) == ["HTN03"]
    assert mapped_rule_ids(by_id["HM10"], rules) == ["HTN05"]
    assert mapped_rule_ids(by_id["HM19"], rules) == ["MED06"]


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        (HistoryMapping("HMX", 1, "hba1c", "hba1c_at_individual_target", "completion_date"), "clinical interpretation"),
        (HistoryMapping("HMX", 1, "lipid_profile", "medication_start_or_change_date", "completion_date"), "value of"),
        (HistoryMapping("HMX", 1, "egfr", "last_hba1c_date", "completion_date"), "no rule in egfr"),
        (HistoryMapping("HMX", 1, "hemoglobin", "last_hba1c_date", "completion_date"), "unknown test"),
        (HistoryMapping("HMX", 1, "hba1c", "last_hba1c_date", "completion_date"), "Duplicate"),
        (HistoryMapping("HMX", 0, "ecg", "encounter_date", "completion_date"), "version"),
        (HistoryMapping("HMX", 1, "ecg", "last_ecg_date", "completion_date", "approved"), "needs a reviewer"),
        (
            HistoryMapping("HMX", 1, "ecg", "last_ecg_date", "completion_date", "approved", reviewer="Synthetic Reviewer"),
            "needs a reviewer",
        ),
        (
            HistoryMapping("HMX", 1, "ecg", "last_ecg_date", "completion_date", reviewer="Synthetic Reviewer"),
            "only an approved mapping",
        ),
    ],
)
def test_invalid_mappings_stop_startup(rules, mapping, message):
    with pytest.raises(ValueError, match=message):
        check_history_mappings(rules.values(), (*HISTORY_MAPPINGS, mapping))


@pytest.mark.parametrize(
    "item",
    [
        AmbiguousHistoryField("egfr", "last_egfr_date", ("DM04",), "Synthetic"),
        AmbiguousHistoryField("egfr", "last_creatinine_date", ("DM99",), "Synthetic"),
        AmbiguousHistoryField("egfr", "last_hba1c_date", ("MED04",), "Synthetic"),
    ],
)
def test_invalid_ambiguous_entries_stop_startup(rules, item):
    with pytest.raises(ValueError, match="Ambiguous"):
        check_history_mappings(rules.values(), HISTORY_MAPPINGS, (*AMBIGUOUS_HISTORY_FIELDS, item))


# Pending mappings leave evaluation unchanged


def test_pending_mappings_never_change_rule_evaluation(rule_set):
    assert evaluate(rule_set, EVERY_TEST_RECORDED) == evaluate(rule_set)


def test_pending_history_is_shown_separately_from_the_evaluation(rule_set):
    tests = summarize(rule_set, [record(7, "egfr", date(2026, 3, 2), "88")])
    egfr = tests["egfr"]
    history = {item.field: item for item in egfr.history_inputs}["last_egfr_date"]

    assert (history.status, history.applied, history.record_count) == ("pending_review", False, 1)
    assert (history.latest_completed_on, history.latest_record_id) == (date(2026, 3, 2), 7)
    assert history.rule_ids == ["DM04", "HTN04", "MED02"]
    for rule in egfr.rules:
        assert missing(rule)["last_egfr_date"] == ("not_collected", False)
    assert {"history_mapping_pending_review", "history_not_used_by_rules"} <= set(egfr.review_reasons)


# Approved mappings


def test_approved_date_mapping_supplies_the_fact_without_changing_status(rule_set):
    before = evaluate(rule_set)
    after = evaluate(rule_set, [record(1, "egfr", date(2026, 3, 2))], approve("HM03"))

    for rule_id in ["DM04", "HTN04", "MED02"]:
        assert "last_egfr_date" not in missing(after[rule_id])
        assert after[rule_id].status == before[rule_id].status


def test_approved_mapping_without_a_record_reports_unknown_never_assumed(rule_set):
    actions = evaluate(rule_set, [], approve("HM03"))

    assert missing(actions["DM04"])["last_egfr_date"] == ("unknown", False)


def test_approved_eligibility_mapping_needs_a_record_and_is_never_negative(rule_set):
    mappings = approve("HM05")

    assert evaluate(rule_set, [record(1, "eye_exam", date(2025, 11, 20))], mappings)["DM07"].status == "candidate"
    without = evaluate(rule_set, [], mappings)["DM07"]
    assert without.status == "needs_information"
    assert missing(without)["last_eye_exam_date"] == ("unknown", True)


def test_test_on_record_mapping_reports_only_presence(rule_set):
    mappings = approve("HM04")

    assert "previous_eye_exam" not in missing(evaluate(rule_set, [record(1, "eye_exam", date(2025, 1, 1))], mappings)["DM05"])
    assert missing(evaluate(rule_set, [], mappings)["DM05"])["previous_eye_exam"] == ("unknown", False)


@pytest.mark.parametrize("result", [None, "92", "منخفض جدًا", "abnormal"])
def test_results_never_affect_evaluation_even_when_approved(rule_set, result):
    baseline = evaluate(rule_set, [record(1, "egfr", date(2026, 1, 1))], approve())

    assert evaluate(rule_set, [record(1, "egfr", date(2026, 1, 1), result)], approve()) == baseline


def test_approved_mapping_never_crosses_into_another_test(rule_set):
    actions = evaluate(rule_set, [record(1, "electrolytes", date(2026, 1, 1))], approve())

    assert "last_electrolytes_date" not in missing(actions["HTN05"])
    assert missing(actions["MED06"])["last_electrolytes_date"] == ("unknown", False)


def test_ambiguous_fields_stay_unfilled_even_with_every_mapping_approved(rule_set):
    actions = evaluate(rule_set, [record(1, "egfr", date(2026, 1, 1)), record(2, "blood_pressure", date(2026, 1, 1))], approve())

    assert missing(actions["MED04"])["last_creatinine_date"] == ("unknown", False)
    assert missing(actions["DM08"])["encounter_date"] == ("not_collected", False)
    assert missing(actions["MED03"])["baseline_creatinine"] == ("not_collected", False)


def test_interpretations_stay_undecided_with_every_mapping_approved(rule_set):
    actions = evaluate(rule_set, [record(1, "hba1c", date(2026, 1, 1), "6.2")], approve())

    assert actions["DM01"].status == actions["DM02"].status == "needs_information"
    assert missing(actions["DM01"])["hba1c_at_individual_target"] == ("not_collected", True)


def test_approving_mappings_never_approves_rules(rule_set):
    uses = [MedicationUse(patient_id=1, medication_id="metformin", dose_text="synthetic")]
    preview = preview_screening(rule_set, Patient(id=1, **PROFILE), uses, TODAY, EVERY_TEST_RECORDED, approve())
    pending = evaluate(rule_set, EVERY_TEST_RECORDED, medications=["metformin"])

    assert preview.clinically_approved is False
    assert preview.auto_schedule_enabled is False
    for action in preview.actions:
        assert action.review_status == "draft_not_clinician_reviewed"
        assert action.auto_schedule_enabled is False
        assert (action.sources, action.conflict_ids, action.review_flags) == (
            pending[action.rule_id].sources,
            pending[action.rule_id].conflict_ids,
            pending[action.rule_id].review_flags,
        )


# Multiple records, missing history, and conflicts


def test_multiple_records_keep_full_history_and_name_the_latest(rule_set):
    records = [record(1, "hba1c", date(2024, 5, 1), "8.1"), record(2, "hba1c", date(2026, 2, 1), "6.9"), record(3, "hba1c", date(2025, 6, 1))]
    hba1c = summarize(rule_set, records, approve("HM01"))["hba1c"]
    history = hba1c.history_inputs[0]

    assert [item.id for item in hba1c.recorded_tests] == [2, 3, 1]
    assert (history.record_count, history.latest_completed_on, history.latest_record_id) == (3, date(2026, 2, 1), 2)
    assert history.applied is True
    assert "history_not_used_by_rules" not in hba1c.review_reasons


def test_missing_history_is_listed_with_no_dates(rule_set):
    for test in summarize(rule_set).values():
        for item in test.history_inputs:
            assert (item.record_count, item.latest_completed_on, item.latest_record_id) == (0, None, None)
        assert "history_mapping_pending_review" not in test.review_reasons


def test_same_day_records_are_kept_and_flagged_without_comparing_results(rule_set):
    records = [record(1, "egfr", date(2026, 3, 2), "88"), record(2, "egfr", date(2026, 3, 2), "61")]
    egfr = summarize(rule_set, records)["egfr"]

    assert [item.result for item in egfr.recorded_tests] == ["61", "88"]
    assert "multiple_records_same_date" in egfr.review_reasons


def test_partly_approved_test_reports_both_states(rule_set):
    tests = summarize(rule_set, [record(1, "lipid_profile", date(2026, 1, 1))], approve("HM11"))
    lipid = tests["lipid_profile"]
    states = {item.field: (item.status, item.applied) for item in lipid.history_inputs}
    rules = {rule.rule_id: rule for rule in lipid.rules}

    assert states == {"last_lipid_profile_date": ("approved", True), "last_lipid_date": ("pending_review", False)}
    assert "last_lipid_profile_date" not in missing(rules["HTN06"])
    assert missing(rules["MED08"])["last_lipid_date"] == ("not_collected", False)
    assert {"history_mapping_pending_review", "history_not_used_by_rules"} <= set(lipid.review_reasons)


def test_ambiguous_fields_are_shown_next_to_the_history(rule_set):
    egfr = summarize(rule_set, [record(1, "egfr", date(2026, 1, 1))])["egfr"]

    assert {item.field for item in egfr.ambiguous_history_fields} == {"last_creatinine_date", "last_renal_date"}
    assert "ambiguous_history_mapping" in egfr.review_reasons


# API


def test_mapping_catalogue_is_published_for_review(client):
    body = client.get("/screening-history-mappings").json()

    assert len(body["mappings"]) == len(HISTORY_MAPPINGS)
    assert {mapping["status"] for mapping in body["mappings"]} == {"pending_review"}
    eye_date = next(mapping for mapping in body["mappings"] if mapping["id"] == "HM05")
    assert (eye_date["rule_ids"], eye_date["changes_eligibility"]) == (["DM07"], True)
    assert len(body["ambiguous"]) == len(AMBIGUOUS_HISTORY_FIELDS)
    assert "hba1c_at_individual_target" in body["clinical_interpretation_fields"]


def test_api_summary_shows_pending_history_while_preview_is_unchanged(client, patient):
    url = f"/patients/{patient['id']}"
    preview_before = client.get(f"{url}/screening-preview").json()
    client.post(
        f"{url}/screening-records",
        json={"test_id": "eye_exam", "test_name": "Retinal exam", "completed_on": "2025-11-20", "source": "clinician_entered"},
    )

    tests = {test["test_id"]: test for test in client.get(f"{url}/screening-summary").json()["tests"]}
    eye = {item["field"]: item for item in tests["eye_exam"]["history_inputs"]}

    assert eye["last_eye_exam_date"]["latest_completed_on"] == "2025-11-20"
    assert eye["last_eye_exam_date"]["applied"] is False
    assert tests["eye_exam"]["needs_information_rule_ids"] == ["DM07"]
    assert client.get(f"{url}/screening-preview").json() == preview_before
