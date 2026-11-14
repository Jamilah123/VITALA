"""Which rule inputs a recorded screening test may provide.

A mapping states a direct fact only: that a test of this kind is on record, or
when it was last completed. A mapping applies to rule evaluation only once it
is approved, and only to rules in its own test group. Results are never read.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.criteria import CRITERIA, rule_input_fields
from app.rules import Rule
from app.screening_tests import RULE_TESTS, SCREENING_TESTS

MappingKind = Literal["completion_date", "test_on_record"]
MappingStatus = Literal["pending_review", "approved"]


@dataclass(frozen=True)
class HistoryMapping:
    id: str
    version: int
    test_id: str
    field: str
    kind: MappingKind
    status: MappingStatus = "pending_review"
    reviewer: str | None = None
    reviewed_on: date | None = None


@dataclass(frozen=True)
class AmbiguousHistoryField:
    test_id: str
    field: str
    rule_ids: tuple[str, ...]
    reason: str


DATE = "completion_date"

HISTORY_MAPPINGS: tuple[HistoryMapping, ...] = (
    HistoryMapping("HM01", 1, "hba1c", "last_hba1c_date", DATE),
    HistoryMapping("HM02", 1, "uacr", "last_uacr_date", DATE),
    HistoryMapping("HM03", 1, "egfr", "last_egfr_date", DATE),
    HistoryMapping("HM04", 1, "eye_exam", "previous_eye_exam", "test_on_record"),
    HistoryMapping("HM05", 1, "eye_exam", "last_eye_exam_date", DATE),
    HistoryMapping("HM06", 1, "foot_exam", "last_foot_exam_date", DATE),
    HistoryMapping("HM07", 1, "neuropathy_exam", "last_neuropathy_exam_date", DATE),
    HistoryMapping("HM08", 1, "bp_followup", "last_review_date", DATE),
    HistoryMapping("HM09", 1, "annual_htn_review", "last_review_date", DATE),
    HistoryMapping("HM10", 1, "electrolytes", "last_electrolytes_date", DATE),
    HistoryMapping("HM11", 1, "lipid_profile", "last_lipid_profile_date", DATE),
    HistoryMapping("HM12", 1, "lipid_profile", "last_lipid_date", DATE),
    HistoryMapping("HM13", 1, "fasting_glucose", "last_fasting_glucose_date", DATE),
    HistoryMapping("HM14", 1, "urine_assessment", "last_urine_assessment_date", DATE),
    HistoryMapping("HM15", 1, "ecg", "last_ecg_date", DATE),
    HistoryMapping("HM16", 1, "vitamin_b12", "last_b12_date", DATE),
    HistoryMapping("HM17", 1, "renal_potassium", "last_creatinine_date", DATE),
    HistoryMapping("HM18", 1, "renal_potassium", "last_potassium_date", DATE),
    HistoryMapping("HM19", 1, "thiazide_labs", "last_electrolytes_date", DATE),
    HistoryMapping("HM20", 1, "thiazide_labs", "last_uric_acid_date", DATE),
    HistoryMapping("HM21", 1, "thiazide_labs", "last_calcium_date", DATE),
    HistoryMapping("HM22", 1, "thiazide_labs", "last_glucose_date", DATE),
    HistoryMapping("HM23", 1, "liver_enzymes", "last_alt_date", DATE),
    HistoryMapping("HM24", 1, "liver_enzymes", "last_ast_date", DATE),
    HistoryMapping("HM25", 1, "ck", "last_ck_date", DATE),
    HistoryMapping("HM26", 1, "inr", "last_inr_date", DATE),
    HistoryMapping("HM27", 1, "cbc_lft_renal", "last_cbc_date", DATE),
    HistoryMapping("HM28", 1, "cbc_lft_renal", "last_lft_date", DATE),
    HistoryMapping("HM29", 1, "cbc_lft_renal", "last_renal_date", DATE),
)

AMBIGUOUS_HISTORY_FIELDS: tuple[AmbiguousHistoryField, ...] = (
    AmbiguousHistoryField("blood_pressure", "encounter_date", ("DM08",), "A blood pressure record is not necessarily a primary care visit."),
    AmbiguousHistoryField(
        "renal_potassium", "baseline_creatinine", ("MED03",), "Whether a record is the baseline depends on its timing relative to the medication start."
    ),
    AmbiguousHistoryField(
        "renal_potassium", "baseline_potassium", ("MED03",), "Whether a record is the baseline depends on its timing relative to the medication start."
    ),
    AmbiguousHistoryField("egfr", "last_creatinine_date", ("MED04", "MED05"), "eGFR is calculated from creatinine, but an eGFR record may not report creatinine."),
    AmbiguousHistoryField("renal_potassium", "last_egfr_date", ("DM04", "HTN04", "MED02"), "A creatinine and potassium record may not report eGFR."),
    AmbiguousHistoryField("egfr", "last_renal_date", ("MED14",), "The methotrexate rule may mean a broader kidney panel than eGFR."),
    AmbiguousHistoryField("electrolytes", "last_electrolytes_date", ("MED06",), "The thiazide rule names electrolytes as part of its own panel."),
    AmbiguousHistoryField("fasting_glucose", "last_glucose_date", ("MED06",), "The thiazide rule does not say the glucose test must be fasting."),
    AmbiguousHistoryField("liver_enzymes", "last_lft_date", ("MED14",), "ALT and AST may not cover the full liver function panel."),
    AmbiguousHistoryField("uacr", "last_urine_assessment_date", ("HTN08",), "UACR is one part of a urine assessment."),
)

CLINICAL_INTERPRETATIONS: frozenset[str] = frozenset(
    {
        "hba1c_at_individual_target",
        "known_kidney_disease",
        "renal_status",
        "retinopathy_status",
        "high_risk_foot_status",
        "foot_ulcer_history",
        "bp_control_status",
        "stable_since",
        "inr_stability_since",
        "dose_stability_since",
        "clinical_stability",
        "anemia_status",
        "neuropathy_status",
        "medication_indication",
        "clinician_next_due_date",
        "clinic_next_due_date",
    }
)


def mapped_rule_ids(mapping: HistoryMapping, rules: Mapping[str, Rule]) -> list[str]:
    return [rule_id for rule_id in SCREENING_TESTS[mapping.test_id].rule_ids if mapping.field in rule_input_fields(rules[rule_id])]


def changes_eligibility(mapping: HistoryMapping, rules: Mapping[str, Rule]) -> bool:
    return any(mapping.field in CRITERIA[rule_id].on_record for rule_id in mapped_rule_ids(mapping, rules))


def applied_history(rule: Rule, recorded: Mapping[str, Sequence[object]], mappings: Iterable[HistoryMapping]) -> dict[str, bool]:
    test_id = RULE_TESTS[rule.id]
    fields = rule_input_fields(rule)
    return {
        mapping.field: bool(recorded.get(test_id))
        for mapping in mappings
        if mapping.status == "approved" and mapping.test_id == test_id and mapping.field in fields
    }


def check_history_mappings(
    rules: Iterable[Rule],
    mappings: Sequence[HistoryMapping] = HISTORY_MAPPINGS,
    ambiguous: Sequence[AmbiguousHistoryField] = AMBIGUOUS_HISTORY_FIELDS,
) -> None:
    by_id = {rule.id: rule for rule in rules}
    all_fields = {field for rule in by_id.values() for field in rule_input_fields(rule)}
    errors: list[str] = []

    ids = [mapping.id for mapping in mappings]
    pairs = [(mapping.test_id, mapping.field) for mapping in mappings]
    if len(set(ids)) != len(ids) or len(set(pairs)) != len(pairs):
        errors.append("Duplicate mapping ids or test and field pairs")

    for mapping in mappings:
        if mapping.test_id not in SCREENING_TESTS:
            errors.append(f"{mapping.id}: unknown test {mapping.test_id}")
            continue
        scoped = mapped_rule_ids(mapping, by_id)
        if not scoped:
            errors.append(f"{mapping.id}: no rule in {mapping.test_id} uses {mapping.field}")
        if mapping.field in CLINICAL_INTERPRETATIONS:
            errors.append(f"{mapping.id}: {mapping.field} is a clinical interpretation")
        if any(mapping.field in CRITERIA[rule_id].uncollected for rule_id in scoped):
            errors.append(f"{mapping.id}: eligibility depends on the value of {mapping.field}, not on a record existing")
        if mapping.version < 1:
            errors.append(f"{mapping.id}: version must be 1 or more")
        review = (mapping.reviewer, mapping.reviewed_on)
        if mapping.status == "approved" and None in review:
            errors.append(f"{mapping.id}: an approved mapping needs a reviewer and a review date")
        if mapping.status != "approved" and review != (None, None):
            errors.append(f"{mapping.id}: only an approved mapping may have a reviewer or review date")

    for item in ambiguous:
        if item.test_id not in SCREENING_TESTS or any(
            rule_id not in by_id or item.field not in rule_input_fields(by_id[rule_id]) for rule_id in item.rule_ids
        ):
            errors.append(f"Ambiguous {item.test_id}/{item.field} does not match the rules {list(item.rule_ids)}")
        elif any(
            (mapping.test_id, mapping.field) == (item.test_id, item.field) and set(item.rule_ids) & set(mapped_rule_ids(mapping, by_id))
            for mapping in mappings
        ):
            errors.append(f"Ambiguous {item.test_id}/{item.field} is also mapped for the same rules")

    errors.extend(f"Clinical interpretation {field} is not a rule input" for field in sorted(CLINICAL_INTERPRETATIONS - all_fields))
    if errors:
        raise ValueError("Invalid history mappings: " + "; ".join(errors))
