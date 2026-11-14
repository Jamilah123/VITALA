"""Risk factors reach the screening engine through RiskContext, and change nothing until a mapping is approved."""

from dataclasses import replace
from datetime import date

import pytest

from app.criteria import rule_input_fields
from app.models import (
    ConditionStatus,
    FamilyCondition,
    FamilyRelative,
    Patient,
    PatientRiskProfile,
    Sex,
    SmokingStatus,
    Verification,
    YesNoUnknown,
)
from app.risk_inputs import RISK_INPUT_MAPPINGS, build_risk_context
from app.screening import preview_screening
from tests.scope_helpers import real_rule_set

TODAY = date(2026, 11, 14)
HYPERTENSIVE = Patient(id=1, date_of_birth=date(1980, 1, 1), sex=Sex.female, hypertension_status=ConditionStatus.diagnosed)


@pytest.fixture(scope="module")
def rule_set():
    return real_rule_set()


def context(profile=None, relatives=(), conditions=(), mappings=RISK_INPUT_MAPPINGS, rule_set=None):
    fields = {rule.id: rule_input_fields(rule) for rule in (rule_set or real_rule_set()).active_rules}
    return build_risk_context(profile, relatives, conditions, fields, mappings)


def approved_rm01():
    return tuple(replace(m, status="approved", reviewer="Synthetic Reviewer", reviewed_on=date(2026, 11, 14)) for m in RISK_INPUT_MAPPINGS)


def htn03(rule_set, risk):
    return next(a for a in preview_screening(rule_set, HYPERTENSIVE, [], TODAY, risk=risk).actions if a.rule_id == "HTN03")


def test_no_profile_means_every_fact_is_unknown():
    facts = context().facts
    assert facts and {fact.state for fact in facts.values()} == {"unknown"}
    assert {fact.source for fact in facts.values()} == {Verification.unknown}


@pytest.mark.parametrize(
    ("status", "state"),
    [(SmokingStatus.current, "present"), (SmokingStatus.former, "present"), (SmokingStatus.never, "absent"), (SmokingStatus.unknown, "unknown")],
)
def test_smoking_states(status, state):
    fact = context(PatientRiskProfile(patient_id=1, smoking_status=status)).facts["smoking_status"]
    assert fact.state == state and fact.value == status.value


@pytest.mark.parametrize(("value", "state"), [(YesNoUnknown.yes, "present"), (YesNoUnknown.no, "absent"), (YesNoUnknown.unknown, "unknown")])
def test_yes_no_unknown_is_three_states_never_two(value, state):
    assert context(PatientRiskProfile(patient_id=1, raised_lipids=value)).facts["raised_lipids"].state == state


def test_measurements_and_source_are_carried():
    profile = PatientRiskProfile(patient_id=1, height_cm=160.0, weight_kg=64.0, information_source=Verification.clinically_confirmed)
    facts = context(profile).facts
    assert (facts["bmi"].state, facts["bmi"].value) == ("value", 25.0)
    assert facts["bmi"].source == Verification.clinically_confirmed
    # An empty field has no source, whatever the profile says.
    assert facts["weight_kg"].source == Verification.clinically_confirmed and facts["activity_minutes_per_week"].source == Verification.unknown


def test_pregnancy_is_never_inferred_from_sex():
    # Recorded as male with pregnancy unknown: still unknown, not "absent".
    assert context(PatientRiskProfile(patient_id=1)).facts["pregnancy_status"].state == "unknown"


def test_structured_family_history_counts_distinct_relatives():
    mother = FamilyRelative(id=1, patient_id=1, relationship="mother")
    aunt = FamilyRelative(id=2, patient_id=1, relationship="maternal_aunt")
    conditions = [
        FamilyCondition(id=1, patient_id=1, relative_id=1, category="cancer", condition="breast", verification=Verification.patient_reported),
        FamilyCondition(id=2, patient_id=1, relative_id=1, category="cancer", condition="ovarian", verification=Verification.clinically_confirmed),
        FamilyCondition(id=3, patient_id=1, relative_id=2, category="cancer", condition="colorectal"),
    ]
    fact = context(None, [mother, aunt], conditions).facts["family_cancer_history"]
    assert fact.state == "present"
    assert fact.detail == {"affected_relatives": 2, "first_degree_relatives": 1, "records": 3}
    assert fact.source == Verification.clinically_confirmed
    # No chronic records: that flag stays unknown rather than becoming absent.
    assert context(None, [mother, aunt], conditions).facts["family_chronic_or_autoimmune_history"].state == "unknown"


def test_only_rules_that_name_a_field_are_listed_and_none_is_actionable():
    facts = context(PatientRiskProfile(patient_id=1, pregnancy_status=YesNoUnknown.no)).facts
    assert facts["pregnancy_status"].rule_ids == ("DM07", "HTN03")
    assert not any(fact.actionable_rule_ids for fact in facts.values())


@pytest.mark.parametrize("pregnancy", list(YesNoUnknown))
def test_pending_mapping_leaves_htn03_undecided_whatever_is_recorded(rule_set, pregnancy):
    action = htn03(rule_set, context(PatientRiskProfile(patient_id=1, pregnancy_status=pregnancy)))
    assert action.status == "needs_information"
    assert {m.field: m.affects_eligibility for m in action.missing_inputs}["pregnancy_status"] is True


@pytest.mark.parametrize(
    ("pregnancy", "status", "reason"),
    [
        (YesNoUnknown.no, "candidate", None),
        (YesNoUnknown.yes, "not_applicable", "pregnancy_status_yes"),
        (YesNoUnknown.unknown, "needs_information", None),
    ],
)
def test_an_approved_mapping_applies_the_value_and_unknown_stays_undecided(rule_set, pregnancy, status, reason):
    risk = context(PatientRiskProfile(patient_id=1, pregnancy_status=pregnancy), mappings=approved_rm01())
    action = htn03(rule_set, risk)
    assert action.status == status
    if reason:
        assert action.reasons == [reason]
    deciding = {m.field for m in action.missing_inputs if m.affects_eligibility}
    if pregnancy == YesNoUnknown.unknown:
        assert "pregnancy_status" in deciding  # unknown is never treated as "not pregnant"
    else:
        assert "pregnancy_status" not in deciding


def test_approved_not_pregnant_makes_htn03_a_candidate_only_with_every_other_condition_met(rule_set):
    risk = context(PatientRiskProfile(patient_id=1, pregnancy_status=YesNoUnknown.no), mappings=approved_rm01())
    action = htn03(rule_set, risk)
    # HTN03 has no other undecided eligibility input, so the approved value completes it.
    assert action.status == "candidate"
    assert action.auto_schedule_enabled is False


def test_an_approval_for_one_rule_does_not_leak_to_another(rule_set):
    risk = context(PatientRiskProfile(patient_id=1, pregnancy_status=YesNoUnknown.no), mappings=approved_rm01())
    actions = {a.rule_id: a for a in preview_screening(rule_set, HYPERTENSIVE, [], TODAY, risk=risk).actions}
    dm07_missing = {m.field: m.reason for m in actions["DM07"].missing_inputs}
    # DM07 is not hypertension-based and its mapping is not approved.
    assert actions["DM07"].status in {"not_applicable", "needs_information"}
    if "pregnancy_status" in dm07_missing:
        assert dm07_missing["pregnancy_status"] == "recorded_pending_review"
