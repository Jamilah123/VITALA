"""Structured medical history: vocabulary, consistency rules and the aggregate read model.

Nothing here is clinical logic. These are data-entry rules:
  * A summary flag set to "no" is a confirmed negative. It cannot coexist with a
    structured record that says otherwise, in either order of entry.
  * "unknown" is never turned into "no", and a record never silently changes a flag.
    Where a record refines an unknown flag, a consistency note says so.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlmodel import Session, select

from app.criteria import rule_input_fields
from app.models import (
    AllergenCategory,
    Allergy,
    AllergySeverity,
    FamilyCondition,
    FamilyConditionCategory,
    FamilyRelationship,
    FamilyRelative,
    GeneticFinding,
    PatientRiskProfile,
    Verification,
    YesNoUnknown,
)
from app.risk_inputs import RiskContext, build_risk_context, relationship_degree
from app.rules import RuleSet
from app.schemas import (
    AllergyRead,
    ConsistencyNote,
    FamilyConditionRead,
    FamilyHistoryCounts,
    FamilyRelativeRead,
    GeneticFindingRead,
    MedicalHistoryRead,
    RiskProfileRead,
    VocabularyRead,
)

CONDITIONS: dict[str, tuple[str, ...]] = {
    "cancer": (
        "breast",
        "ovarian",
        "colorectal",
        "prostate",
        "pancreatic",
        "endometrial",
        "stomach",
        "lung",
        "thyroid",
        "blood_cancer",
        "melanoma",
        "other",
        "unknown_type",
    ),
    "chronic": (
        "type_1_diabetes",
        "type_2_diabetes",
        "diabetes_type_unknown",
        "hypertension",
        "coronary_heart_disease",
        "heart_failure",
        "stroke",
        "chronic_kidney_disease",
        "high_cholesterol",
        "obesity",
        "asthma",
        "copd",
        "other",
    ),
    "autoimmune": (
        "rheumatoid_arthritis",
        "systemic_lupus",
        "celiac_disease",
        "multiple_sclerosis",
        "autoimmune_thyroid",
        "inflammatory_bowel_disease",
        "psoriasis",
        "other",
    ),
}


@dataclass(frozen=True)
class FlagMapping:
    """Which structured family records a risk-profile summary flag covers."""

    flag: str
    categories: frozenset[str]
    conditions: frozenset[str] | None  # None: every condition in those categories


# Backward-compatible mapping between the older yes/no family flags and the structured records.
FAMILY_FLAG_MAPPINGS: tuple[FlagMapping, ...] = (
    FlagMapping("family_diabetes", frozenset({"chronic"}), frozenset({"type_1_diabetes", "type_2_diabetes", "diabetes_type_unknown"})),
    FlagMapping("family_heart_disease", frozenset({"chronic"}), frozenset({"coronary_heart_disease", "heart_failure"})),
    FlagMapping("family_breast_cancer", frozenset({"cancer"}), frozenset({"breast"})),
    FlagMapping("family_colorectal_cancer", frozenset({"cancer"}), frozenset({"colorectal"})),
    FlagMapping("family_cancer_history", frozenset({"cancer"}), None),
    FlagMapping("family_chronic_or_autoimmune_history", frozenset({"chronic", "autoimmune"}), None),
)


def normalize_allergen(name: str) -> str:
    return " ".join(name.casefold().split())


def condition_errors(category: str, condition: str, condition_other: str | None) -> dict[str, str]:
    allowed = CONDITIONS[category]
    if condition not in allowed:
        return {"condition": f"'{condition}' is not a {category} condition. Use one of: {', '.join(allowed)}"}
    if condition == "other" and not condition_other:
        return {"condition_other": "Describe the condition when condition is 'other'"}
    if condition != "other" and condition_other:
        return {"condition_other": "condition_other is only for condition 'other'"}
    return {}


def _covers(mapping: FlagMapping, category: str, condition: str) -> bool:
    return category in mapping.categories and (mapping.conditions is None or condition in mapping.conditions)


def flags_contradicted_by(category: str, condition: str, profile: PatientRiskProfile | None) -> dict[str, str]:
    """Errors when a new family record contradicts a flag recorded as a confirmed 'no'."""
    if profile is None:
        return {}
    return {
        mapping.flag: f"{mapping.flag} is recorded as 'no'. Change it before adding this record."
        for mapping in FAMILY_FLAG_MAPPINGS
        if _covers(mapping, category, condition) and getattr(profile, mapping.flag) == YesNoUnknown.no
    }


def negative_flag_errors(
    profile: Mapping[str, object],
    conditions: Iterable[FamilyCondition],
    allergy_count: int,
    genetic_count: int,
) -> dict[str, str]:
    """Errors when a profile would say 'no' while structured records say otherwise."""
    errors: dict[str, str] = {}
    conditions = list(conditions)
    for mapping in FAMILY_FLAG_MAPPINGS:
        if profile.get(mapping.flag) == YesNoUnknown.no and any(_covers(mapping, c.category, c.condition) for c in conditions):
            errors[mapping.flag] = "Cannot be 'no' while matching family history records exist"
    if profile.get("known_allergies") == YesNoUnknown.no and allergy_count:
        errors["known_allergies"] = "Cannot be 'no' while allergy records exist"
    if profile.get("known_genetic_findings") == YesNoUnknown.no and genetic_count:
        errors["known_genetic_findings"] = "Cannot be 'no' while genetic findings exist"
    return errors


def consistency_notes(
    profile: PatientRiskProfile | None,
    conditions: Iterable[FamilyCondition],
    allergy_count: int,
    genetic_count: int,
) -> list[ConsistencyNote]:
    """Non-blocking notes where a record exists but its summary flag is still unknown."""
    stored = profile or PatientRiskProfile(patient_id=0)
    conditions = list(conditions)
    notes = []
    for mapping in FAMILY_FLAG_MAPPINGS:
        count = sum(1 for c in conditions if _covers(mapping, c.category, c.condition))
        if count and getattr(stored, mapping.flag) == YesNoUnknown.unknown:
            notes.append(ConsistencyNote(field=mapping.flag, message=f"{count} structured record(s) exist; the summary flag is still unknown"))
    for flag, count in (("known_allergies", allergy_count), ("known_genetic_findings", genetic_count)):
        if count and getattr(stored, flag) == YesNoUnknown.unknown:
            notes.append(ConsistencyNote(field=flag, message=f"{count} record(s) exist; the summary flag is still unknown"))
    return notes


def vocabulary() -> VocabularyRead:
    return VocabularyRead(
        relationships=[item.value for item in FamilyRelationship],
        conditions={category: list(items) for category, items in CONDITIONS.items()},
        allergen_categories=[item.value for item in AllergenCategory],
        allergy_severities=[item.value for item in AllergySeverity],
        verification=[item.value for item in Verification],
    )


# ---------------------------------------------------------------- loading


@dataclass(frozen=True)
class HistoryRecords:
    profile: PatientRiskProfile | None
    allergies: list[Allergy]
    relatives: list[FamilyRelative]
    conditions: list[FamilyCondition]
    genetic: list[GeneticFinding]


def load_history(session: Session, patient_id: int) -> HistoryRecords:
    def rows(model):
        return list(session.exec(select(model).where(model.patient_id == patient_id).order_by(model.id)).all())

    return HistoryRecords(
        profile=session.get(PatientRiskProfile, patient_id),
        allergies=rows(Allergy),
        relatives=rows(FamilyRelative),
        conditions=rows(FamilyCondition),
        genetic=rows(GeneticFinding),
    )


def risk_context_for(records: HistoryRecords, rule_set: RuleSet) -> RiskContext:
    rule_fields = {rule.id: rule_input_fields(rule) for rule in rule_set.active_rules}
    return build_risk_context(records.profile, records.relatives, records.conditions, rule_fields)


def patient_risk_context(session: Session, patient_id: int, rule_set: RuleSet) -> RiskContext:
    return risk_context_for(load_history(session, patient_id), rule_set)


def relative_read(relative: FamilyRelative, conditions: Iterable[FamilyCondition]) -> FamilyRelativeRead:
    return FamilyRelativeRead(
        id=relative.id,
        patient_id=relative.patient_id,
        relationship=relative.relationship,
        degree=relationship_degree(relative.relationship),
        label=relative.label,
        conditions=[
            FamilyConditionRead.model_validate(condition, from_attributes=True)
            for condition in conditions
            if condition.relative_id == relative.id
        ],
    )


def family_counts(records: HistoryRecords) -> FamilyHistoryCounts:
    by_id = {relative.id: relative for relative in records.relatives}
    cancer = {c.relative_id for c in records.conditions if c.category == FamilyConditionCategory.cancer}
    other = {c.relative_id for c in records.conditions if c.category != FamilyConditionCategory.cancer}
    return FamilyHistoryCounts(
        relatives_with_cancer=len(cancer),
        first_degree_relatives_with_cancer=sum(1 for rid in cancer if relationship_degree(by_id[rid].relationship) == "first"),
        relatives_with_chronic_or_autoimmune=len(other),
    )


def medical_history_read(session: Session, patient_id: int, rule_set: RuleSet, risk_profile: RiskProfileRead) -> MedicalHistoryRead:
    # Imported here to avoid a cycle: screening.py imports this module's dependencies.
    from app.screening import risk_fact_reads

    records = load_history(session, patient_id)
    return MedicalHistoryRead(
        patient_id=patient_id,
        risk_profile=risk_profile,
        allergies=[AllergyRead.model_validate(item, from_attributes=True) for item in records.allergies],
        family_relatives=[relative_read(relative, records.conditions) for relative in records.relatives],
        family_counts=family_counts(records),
        genetic_findings=[GeneticFindingRead.model_validate(item, from_attributes=True) for item in records.genetic],
        risk_factors=risk_fact_reads(risk_context_for(records, rule_set)),
        consistency_notes=consistency_notes(records.profile, records.conditions, len(records.allergies), len(records.genetic)),
    )
