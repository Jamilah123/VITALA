from datetime import date

import pytest

from tests.scope_helpers import full_scope_rule_set

from app.models import ConditionStatus, DiabetesType, MedicationUse, Patient, RecordSource, ScreeningRecord
from app.screening import preview_screening, summarize_screening
from app.screening_tests import POSSIBLE_OVERLAPS, SCREENING_TESTS, check_test_mapping

TODAY = date(2026, 11, 4)
DIAGNOSED = ConditionStatus.diagnosed

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


def use(medication_id):
    return MedicationUse(patient_id=1, medication_id=medication_id, dose_text="synthetic")


def record(record_id, test_id, completed_on, result=None, unit=None):
    return ScreeningRecord(
        id=record_id,
        patient_id=1,
        test_id=test_id,
        test_name=test_id,
        completed_on=completed_on,
        result=result,
        unit=unit,
        source=RecordSource.lab_report,
    )


def summarize(rule_set, uses=(), records=(), **profile):
    summary = summarize_screening(rule_set, Patient(id=1, **profile), list(uses), list(records), TODAY)
    return summary, {test.test_id: test for test in summary.tests}


def all_keys(value):
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in all_keys(item)}
    return set()


# Explicit mapping


def test_every_rule_belongs_to_exactly_one_test(rule_set):
    check_test_mapping(rule_set.rules)

    with pytest.raises(ValueError, match="exactly one"):
        check_test_mapping(rule_set.rules[1:])
    with pytest.raises(ValueError, match="exactly one"):
        check_test_mapping([*rule_set.rules, rule_set.rules[0]])


def test_groups_never_merge_different_research_action_ids(rule_set):
    rules = {rule.id: rule for rule in rule_set.rules}

    for test_id, test in SCREENING_TESTS.items():
        assert len({rules[rule_id].action_id for rule_id in test.rule_ids}) == 1, test_id


@pytest.mark.parametrize(
    ("first", "second"),
    [("HTN04", "MED03"), ("DM03", "HTN08"), ("HTN05", "MED03"), ("HTN05", "MED06"), ("DM09", "DM10"), ("DM08", "HTN01")],
)
def test_partly_overlapping_tests_stay_separate_and_are_declared(first, second):
    owner = {rule_id: test_id for test_id, test in SCREENING_TESTS.items() for rule_id in test.rule_ids}

    assert owner[first] != owner[second]
    assert tuple(sorted((owner[first], owner[second]))) in {tuple(sorted(pair)) for pair in POSSIBLE_OVERLAPS}


# Duplicate rules for one test


def test_duplicate_rules_for_one_test_are_grouped_and_each_is_preserved(rule_set):
    _, tests = summarize(rule_set, [use("metformin")], hypertension_status=DIAGNOSED, **TYPE_2_DIABETES)
    egfr = tests["egfr"]

    assert [rule.rule_id for rule in egfr.rules] == ["DM04", "HTN04", "MED02"]
    assert egfr.candidate_rule_ids == ["DM04", "MED02"]
    assert egfr.needs_information_rule_ids == ["HTN04"]
    assert [source.source_id for source in egfr.rules[0].sources] == ["S01", "S02"]
    assert egfr.rules[1].conflict_ids == ["C03"]
    assert {rule.review_status for rule in egfr.rules} == {"draft_not_clinician_reviewed"}


def test_summary_rules_match_the_preview_exactly(rule_set):
    patient = Patient(id=1, hypertension_status=DIAGNOSED, **TYPE_2_DIABETES)
    uses = [use("metformin"), use("losartan"), use("warfarin")]

    preview = preview_screening(rule_set, patient, uses, TODAY)
    summary = summarize_screening(rule_set, patient, uses, [], TODAY)
    grouped = {rule.rule_id: rule for test in summary.tests for rule in test.rules}

    assert len(grouped) == len(preview.actions) == sum(len(test.rules) for test in summary.tests)
    for action in preview.actions:
        assert grouped[action.rule_id] == action


def test_missing_inputs_are_combined_with_the_rules_that_need_them(rule_set):
    _, tests = summarize(rule_set, **TYPE_2_DIABETES)
    missing = {item.field: item for item in tests["hba1c"].missing_inputs}

    assert missing["hba1c_at_individual_target"].rule_ids == ["DM01", "DM02"]
    assert missing["hba1c_at_individual_target"].affects_eligibility is True
    assert missing["hba1c_at_individual_target"].reason == "not_collected"
    assert missing["last_hba1c_date"].affects_eligibility is False


# Conflicting rule statuses


def test_conflicting_rule_statuses_are_kept_apart_and_flagged(rule_set):
    _, tests = summarize(rule_set, **TYPE_2_DIABETES)
    eye = tests["eye_exam"]

    assert eye.candidate_rule_ids == ["DM05"]
    assert eye.not_applicable_rule_ids == ["DM06"]
    assert eye.needs_information_rule_ids == ["DM07"]
    assert {"mixed_rule_statuses", "source_conflict", "draft_test_grouping", "draft_rules"} <= set(eye.review_reasons)
    assert eye.conflict_ids == ["C01"]


def test_context_dependent_alternatives_are_not_flagged_as_mixed(rule_set):
    _, tests = summarize(rule_set, [use("losartan")], **TYPE_2_DIABETES)
    renal = tests["renal_potassium"]

    assert renal.candidate_rule_ids == ["MED03", "MED04"]
    assert renal.not_applicable_rule_ids == ["MED05"]
    assert "mixed_rule_statuses" not in renal.review_reasons


# Missing and multiple history


def test_missing_history_is_reported_as_empty_never_as_negative(rule_set):
    summary, tests = summarize(rule_set, **TYPE_2_DIABETES)

    assert all(test.recorded_tests == [] for test in summary.tests)
    assert summary.unmapped_records == []
    assert tests["hba1c"].needs_information_rule_ids == ["DM01", "DM02"]
    assert "history_not_used_by_rules" not in tests["hba1c"].review_reasons


def test_multiple_results_are_all_shown_newest_first(rule_set):
    records = [
        record(1, "hba1c", date(2025, 1, 10), "8.4", "%"),
        record(2, "hba1c", date(2026, 2, 3), "7.1", "%"),
        record(3, "hba1c", date(2025, 7, 20), "7.6", "%"),
        record(4, "egfr", date(2026, 2, 3), "92", "mL/min/1.73m²"),
    ]
    _, tests = summarize(rule_set, records=records, **TYPE_2_DIABETES)

    assert [item.id for item in tests["hba1c"].recorded_tests] == [2, 3, 1]
    assert [item.result for item in tests["hba1c"].recorded_tests] == ["7.1", "7.6", "8.4"]
    assert [item.id for item in tests["egfr"].recorded_tests] == [4]
    assert "history_not_used_by_rules" in tests["hba1c"].review_reasons


@pytest.mark.parametrize("result", ["5.0", "12.5", "مرتفع"])
def test_results_never_change_rule_evaluation(rule_set, result):
    _, without = summarize(rule_set, **TYPE_2_DIABETES)
    _, with_result = summarize(rule_set, records=[record(1, "hba1c", date(2026, 1, 1), result, "%")], **TYPE_2_DIABETES)

    assert with_result["hba1c"].rules == without["hba1c"].rules
    assert with_result["hba1c"].needs_information_rule_ids == ["DM01", "DM02"]


def test_records_without_applicable_rules_are_still_shown(rule_set):
    _, tests = summarize(rule_set, records=[record(1, "inr", date(2026, 5, 1), "2.4")], **TYPE_2_DIABETES)
    inr = tests["inr"]

    assert [item.result for item in inr.recorded_tests] == ["2.4"]
    assert inr.not_triggered_rule_ids == ["MED11", "MED12", "MED13"]
    assert "history_not_used_by_rules" not in inr.review_reasons


def test_records_for_unmapped_tests_are_never_dropped(rule_set):
    summary, _ = summarize(rule_set, records=[record(1, "retired_test", date(2026, 1, 1))])

    assert [item.test_id for item in summary.unmapped_records] == ["retired_test"]


def test_tests_that_do_not_concern_the_patient_have_no_review_items(rule_set):
    _, tests = summarize(rule_set, **TYPE_2_DIABETES)

    assert tests["inr"].review_reasons == []
    assert tests["inr"].not_triggered_rule_ids == ["MED11", "MED12", "MED13"]


# Safety


def test_summary_is_unapproved_and_calculates_no_due_dates(rule_set):
    summary, _ = summarize(rule_set, [use("warfarin")], [record(1, "inr", date(2026, 5, 1), "2.4")], **TYPE_2_DIABETES)
    body = summary.model_dump(mode="json")

    assert body["clinically_approved"] is False
    assert body["auto_schedule_enabled"] is False
    assert {test["mapping_status"] for test in body["tests"]} == {"draft_not_clinician_reviewed"}
    keys = all_keys(body)
    assert not {key for key in keys if "due" in key or "next" in key}
    assert "schedule" not in keys


# API


def test_summary_for_a_missing_patient_returns_404(client):
    assert client.get("/patients/999/screening-summary").status_code == 404


def test_summary_uses_stored_records_and_leaves_the_preview_unchanged(client, patient):
    url = f"/patients/{patient['id']}"
    client.post(f"{url}/medications", json={"medication_id": "metformin", "dose_text": "500 mg"})
    preview_before = client.get(f"{url}/screening-preview").json()

    for completed_on, result in [("2025-09-01", "7.4"), ("2026-03-01", "6.9")]:
        client.post(
            f"{url}/screening-records",
            json={"test_id": "hba1c", "test_name": "HbA1c", "completed_on": completed_on, "result": result, "unit": "%", "source": "lab_report"},
        )

    response = client.get(f"{url}/screening-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == patient["id"]
    assert body["evaluated_on"] == date.today().isoformat()
    tests = {test["test_id"]: test for test in body["tests"]}
    assert list(tests) == list(SCREENING_TESTS)
    assert [item["result"] for item in tests["hba1c"]["recorded_tests"]] == ["6.9", "7.4"]
    assert tests["vitamin_b12"]["candidate_rule_ids"] == ["MED01"]
    assert client.get(f"{url}/screening-preview").json() == preview_before
