"""Evaluate the draft rules against one patient's recorded data.

The result is a preview for review, never a recommendation or a schedule.
Unknown data yields "needs_information", never a negative finding.
"""

from collections.abc import Mapping, Sequence
from datetime import date

from app.criteria import CRITERIA, DIAGNOSED, INPUT_ALIASES, TYPE_1, Criteria, rule_input_fields
from app.history_mappings import (
    AMBIGUOUS_HISTORY_FIELDS,
    HISTORY_MAPPINGS,
    HistoryMapping,
    applied_history,
    changes_eligibility,
    mapped_rule_ids,
)
from app.models import ConditionStatus, DiabetesType, MedicationUse, Patient, ScreeningRecord
from app.risk_inputs import EMPTY_RISK_CONTEXT, RISK_FIELDS, RiskContext
from app.rules import Rule, RuleSet
from app.schemas import (
    AmbiguousHistoryFieldRead,
    OutOfScopeMedication,
    RiskFactRead,
    HistoryInput,
    MissingInput,
    ScreeningAction,
    ScreeningPreview,
    ScreeningRecordRead,
    ScreeningSummary,
    ScreeningTestSummary,
    SourceReference,
    SummaryMissingInput,
)
from app.screening_tests import SCREENING_TESTS, ScreeningTest, possible_overlaps

NOTICE_AR = (
    "معاينة تجريبية لقواعد مسودة لم يراجعها طبيب. ليست توصية طبية ولا تُنشئ مواعيد. "
    "عدم انطباق قاعدة أو غياب دواء من السجل لا يعني أن الفحص غير لازم."
)

UNKNOWN = ConditionStatus.unknown


def full_years(start: date, today: date) -> int:
    return today.year - start.year - ((today.month, today.day) < (start.month, start.day))



def _known_inputs(patient: Patient, uses: Sequence[MedicationUse]) -> dict[str, bool]:
    # Every input VITALA records. Any other input a rule names is not collected.
    return {
        "date_of_birth": patient.date_of_birth is not None,
        "diabetes_status": patient.diabetes_status != UNKNOWN,
        "diabetes_type": patient.diabetes_type != DiabetesType.unknown,
        "diabetes_diagnosis_date": patient.diabetes_diagnosis_date is not None,
        "hypertension_status": patient.hypertension_status != UNKNOWN,
        "medication_start_date": bool(uses) and all(use.start_date for use in uses),
    }


def _check_eligibility(
    rule: Rule,
    criteria: Criteria,
    patient: Patient,
    known: Mapping[str, bool],
    today: date,
    risk: RiskContext = EMPTY_RISK_CONTEXT,
) -> tuple[list[str], list[str]]:
    """Return the facts that exclude the rule, and the unknown fields that leave it undecided."""
    excluded: list[str] = []
    unknown: list[str] = []

    def require_status(condition: str, required: ConditionStatus) -> None:
        status = getattr(patient, f"{condition}_status")
        if status == UNKNOWN:
            unknown.append(f"{condition}_status")
        elif status != required:
            excluded.append(f"{condition}_{status}")

    if rule.track != "medication":
        require_status(rule.track, DIAGNOSED)
    if criteria.diabetes:
        require_status("diabetes", criteria.diabetes)

    if criteria.diabetes_types:
        diabetes_type = patient.diabetes_type
        if diabetes_type == DiabetesType.unknown:
            unknown.append("diabetes_type")
        elif diabetes_type not in criteria.diabetes_types:
            excluded.append("diabetes_type_not_covered")
        elif diabetes_type == TYPE_1 and criteria.type_1_min_years:
            diagnosed_on = patient.diabetes_diagnosis_date
            if diagnosed_on is None:
                unknown.append("diabetes_diagnosis_date")
            elif full_years(diagnosed_on, today) < criteria.type_1_min_years:
                excluded.append("diabetes_duration_below_minimum")

    if criteria.min_age:
        if patient.date_of_birth is None:
            unknown.append("date_of_birth")
        elif full_years(patient.date_of_birth, today) < criteria.min_age:
            excluded.append("age_below_minimum")

    for field, required in criteria.risk_required:
        # Without an approved mapping the recorded value is not used at all.
        if not risk.approved(rule.id, field) or risk.state(field) == "unknown":
            unknown.append(field)
        elif risk.value(field) != required:
            excluded.append(f"{field}_{risk.value(field)}")

    unknown.extend(field for field in criteria.on_record if not known.get(field))
    unknown.extend(criteria.uncollected)
    return excluded, unknown


def _missing_reason(field: str, known: Mapping[str, bool], risk: RiskContext) -> str:
    if field in RISK_FIELDS:
        # VITALA records risk factors. Empty is "unknown"; a stored value that no
        # approved mapping lets the rules use is "recorded_pending_review".
        return "unknown" if risk.state(field) == "unknown" else "recorded_pending_review"
    return "unknown" if field in known else "not_collected"


def _risk_known(rule: Rule, risk: RiskContext) -> dict[str, bool]:
    return {
        field: risk.approved(rule.id, field) and risk.state(field) != "unknown"
        for field in rule_input_fields(rule)
        if field in RISK_FIELDS
    }


def _source_reference(rule_set: RuleSet, source_id: str, locator: str) -> SourceReference:
    source = rule_set.sources[source_id]
    return SourceReference(
        source_id=source_id,
        locator=locator,
        title=source.title,
        issuer=source.issuer,
        url=source.url,
        version=source.version,
        limitation_ar=source.limitation_ar,
    )


def evaluate_rule(
    rule_set: RuleSet,
    rule: Rule,
    patient: Patient,
    uses: Sequence[MedicationUse],
    today: date,
    history: Mapping[str, bool] | None = None,
    risk: RiskContext = EMPTY_RISK_CONTEXT,
) -> ScreeningAction:
    # Archived catalogue entries never trigger a rule, even when they are recorded.
    active_drug_ids = rule_set.active_drug_ids(rule)
    matched = [use for use in uses if use.medication_id in active_drug_ids]
    missing: list[MissingInput] = []

    if rule.track == "medication" and not matched:
        status, reasons = "not_triggered", ["no_matching_medication_recorded"]
    else:
        known = _known_inputs(patient, matched) | dict(history or {}) | _risk_known(rule, risk)
        reasons, undecided = _check_eligibility(rule, CRITERIA[rule.id], patient, known, today, risk)
        if reasons:
            status = "not_applicable"
        else:
            status = "needs_information" if undecided else "candidate"
            inputs = [INPUT_ALIASES.get(field, field) for field in rule.required_inputs]
            missing = [
                MissingInput(
                    field=field,
                    reason=_missing_reason(field, known, risk),
                    affects_eligibility=field in undecided,
                )
                for field in dict.fromkeys([*inputs, *undecided])
                if not known.get(field)
            ]

    return ScreeningAction(
        rule_id=rule.id,
        track=rule.track,
        action_id=rule.action_id,
        action_name_ar=rule.action_name_ar,
        eligibility_ar=rule.eligibility_ar,
        status=status,
        reasons=reasons,
        missing_inputs=missing,
        matched_medication_ids=sorted(use.medication_id for use in matched),
        schedule_text_ar=rule.schedule.text_ar,
        notes_ar=rule.notes_ar,
        review_flags=rule.review_flags,
        conflict_ids=[conflict.id for conflict in rule_set.conflicts if rule.id in conflict.rule_ids],
        knowledge_ids=rule.knowledge_ids,
        sources=[_source_reference(rule_set, item.source_id, item.locator) for item in rule.evidence],
        review_status=rule.clinical_status,
        auto_schedule_enabled=rule.auto_schedule_enabled,
    )


def _records_by_test(records: Sequence[ScreeningRecord]) -> dict[str, list[ScreeningRecordRead]]:
    recorded: dict[str, list[ScreeningRecordRead]] = {}
    for record in sorted(records, key=lambda record: (record.completed_on, record.id), reverse=True):
        recorded.setdefault(record.test_id, []).append(ScreeningRecordRead.model_validate(record, from_attributes=True))
    return recorded


def _evaluate_all(
    rule_set: RuleSet,
    patient: Patient,
    uses: Sequence[MedicationUse],
    recorded: Mapping[str, Sequence[ScreeningRecordRead]],
    mappings: Sequence[HistoryMapping],
    today: date,
    risk: RiskContext = EMPTY_RISK_CONTEXT,
) -> list[ScreeningAction]:
    # Archived rules are kept for reference but never evaluated.
    return [
        evaluate_rule(rule_set, rule, patient, uses, today, applied_history(rule, recorded, mappings), risk)
        for rule in rule_set.active_rules
    ]


def risk_fact_reads(risk: RiskContext) -> list[RiskFactRead]:
    return [
        RiskFactRead(
            field=fact.field,
            state=fact.state,
            value=fact.value,
            source=fact.source,
            rule_ids=list(fact.rule_ids),
            actionable=bool(fact.actionable_rule_ids),
            actionable_rule_ids=list(fact.actionable_rule_ids),
            detail=dict(fact.detail),
        )
        for fact in risk.facts.values()
    ]


def out_of_scope_medications(rule_set: RuleSet, uses: Sequence[MedicationUse]) -> list[OutOfScopeMedication]:
    return [
        OutOfScopeMedication(use_id=use.id, medication_id=use.medication_id)
        for use in uses
        if use.medication_id in rule_set.archived_medication_ids
    ]


def preview_screening(
    rule_set: RuleSet,
    patient: Patient,
    uses: Sequence[MedicationUse],
    today: date,
    records: Sequence[ScreeningRecord] = (),
    mappings: Sequence[HistoryMapping] = HISTORY_MAPPINGS,
    risk: RiskContext = EMPTY_RISK_CONTEXT,
) -> ScreeningPreview:
    return ScreeningPreview(
        patient_id=patient.id,
        evaluated_on=today,
        notice_ar=NOTICE_AR,
        actions=_evaluate_all(rule_set, patient, uses, _records_by_test(records), mappings, today, risk),
        risk_factors=risk_fact_reads(risk),
        out_of_scope_medications=out_of_scope_medications(rule_set, uses),
    )


def _history_inputs(
    test_id: str,
    recorded: list[ScreeningRecordRead],
    mappings: Sequence[HistoryMapping],
    rules: Mapping[str, Rule],
) -> list[HistoryInput]:
    latest = recorded[0] if recorded else None
    return [
        HistoryInput(
            mapping_id=mapping.id,
            version=mapping.version,
            field=mapping.field,
            kind=mapping.kind,
            status=mapping.status,
            applied=mapping.status == "approved",
            changes_eligibility=changes_eligibility(mapping, rules),
            rule_ids=mapped_rule_ids(mapping, rules),
            record_count=len(recorded),
            latest_completed_on=latest.completed_on if latest else None,
            latest_record_id=latest.id if latest else None,
        )
        for mapping in mappings
        if mapping.test_id == test_id
    ]


def _summarize_test(
    test_id: str,
    test: ScreeningTest,
    rules: list[ScreeningAction],
    recorded: list[ScreeningRecordRead],
    history: list[HistoryInput],
    archived_rule_ids: list[str] | None = None,
) -> ScreeningTestSummary:
    def rule_ids(status: str) -> list[str]:
        return [rule.rule_id for rule in rules if rule.status == status]

    missing: dict[str, SummaryMissingInput] = {}
    for rule in rules:
        for item in rule.missing_inputs:
            entry = missing.setdefault(
                item.field,
                SummaryMissingInput(field=item.field, reason=item.reason, affects_eligibility=False, rule_ids=[]),
            )
            entry.affects_eligibility = entry.affects_eligibility or item.affects_eligibility
            entry.rule_ids.append(rule.rule_id)

    candidates, undecided = rule_ids("candidate"), rule_ids("needs_information")
    conflict_ids = sorted({conflict_id for rule in rules for conflict_id in rule.conflict_ids})
    overlaps = possible_overlaps(test_id)
    ambiguous = [
        AmbiguousHistoryFieldRead(test_id=item.test_id, field=item.field, rule_ids=list(item.rule_ids), reason=item.reason)
        for item in AMBIGUOUS_HISTORY_FIELDS
        if item.test_id == test_id
    ]
    history_used = bool(history) and all(item.applied for item in history)
    # Review reasons are given only when the test concerns this patient.
    relevant = bool(candidates or undecided or recorded)
    review_checks = (
        ("draft_rules", any(rule.review_status == "draft_not_clinician_reviewed" for rule in rules)),
        ("draft_test_grouping", len(rules) > 1),
        ("source_conflict", bool(conflict_ids)),
        ("mixed_rule_statuses", bool(candidates and undecided)),
        ("possible_overlap", bool(overlaps)),
        ("history_not_used_by_rules", bool(recorded and (candidates or undecided)) and not history_used),
        ("history_mapping_pending_review", any(item.record_count and item.status == "pending_review" for item in history)),
        ("ambiguous_history_mapping", bool(recorded and ambiguous)),
        ("multiple_records_same_date", len({item.completed_on for item in recorded}) < len(recorded)),
    )

    return ScreeningTestSummary(
        test_id=test_id,
        name_ar=test.name_ar,
        recorded_tests=recorded,
        history_inputs=history,
        ambiguous_history_fields=ambiguous,
        candidate_rule_ids=candidates,
        needs_information_rule_ids=undecided,
        not_applicable_rule_ids=rule_ids("not_applicable"),
        not_triggered_rule_ids=rule_ids("not_triggered"),
        missing_inputs=list(missing.values()),
        review_reasons=[reason for reason, applies in review_checks if relevant and applies],
        conflict_ids=conflict_ids,
        possible_overlap_test_ids=overlaps,
        rules=rules,
        archived_rule_ids=archived_rule_ids or [],
    )


def summarize_screening(
    rule_set: RuleSet,
    patient: Patient,
    uses: Sequence[MedicationUse],
    records: Sequence[ScreeningRecord],
    today: date,
    mappings: Sequence[HistoryMapping] = HISTORY_MAPPINGS,
    risk: RiskContext = EMPTY_RISK_CONTEXT,
) -> ScreeningSummary:
    recorded = _records_by_test(records)
    actions = {action.rule_id: action for action in _evaluate_all(rule_set, patient, uses, recorded, mappings, today, risk)}
    rules = {rule.id: rule for rule in rule_set.rules}
    archived = {rule.id for rule in rule_set.archived_rules}

    return ScreeningSummary(
        patient_id=patient.id,
        evaluated_on=today,
        notice_ar=NOTICE_AR,
        tests=[
            _summarize_test(
                test_id,
                test,
                [actions[rule_id] for rule_id in test.rule_ids if rule_id in actions],
                recorded.get(test_id, []),
                _history_inputs(test_id, recorded.get(test_id, []), mappings, rules),
                [rule_id for rule_id in test.rule_ids if rule_id in archived],
            )
            for test_id, test in SCREENING_TESTS.items()
        ],
        unmapped_records=[record for test_id, items in recorded.items() if test_id not in SCREENING_TESTS for record in items],
        risk_factors=risk_fact_reads(risk),
        out_of_scope_medications=out_of_scope_medications(rule_set, uses),
    )
