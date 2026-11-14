"""Risk-factor facts the screening engine may read, and the gate that decides whether it may use them.

Every recorded risk factor reaches the evaluation as a RiskFact with one of
four states: present, absent, unknown, or value (a measurement). "unknown" is
never read as "absent". Each fact keeps where it came from (patient-reported,
clinically confirmed, or unknown).

A fact can change a rule's eligibility only through a RiskInputMapping whose
status is "approved", and only for the rules that mapping names. No mapping is
approved yet, so risk factors are recorded and reported but do not change any
screening status. This mirrors HISTORY_MAPPINGS in history_mappings.py.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.models import (
    FamilyCondition,
    FamilyConditionCategory,
    FamilyRelative,
    PatientRiskProfile,
    SmokingStatus,
    Verification,
    YesNoUnknown,
)

FactState = Literal["present", "absent", "unknown", "value"]
MappingStatus = Literal["pending_review", "approved"]


@dataclass(frozen=True)
class RiskInputMapping:
    id: str
    version: int
    field: str
    rule_ids: tuple[str, ...]
    note: str
    status: MappingStatus = "pending_review"
    reviewer: str | None = None
    reviewed_on: date | None = None


# Rules whose eligibility text depends on a recorded risk factor. A mapping only
# says the engine may use the stored value for those rules; the condition itself
# lives in criteria.py (risk_required) and is as unreviewed as the rules.
RISK_INPUT_MAPPINGS: tuple[RiskInputMapping, ...] = (
    RiskInputMapping(
        "RM01",
        1,
        "pregnancy_status",
        ("HTN03",),
        "HTN03 eligibility reads 'adult, not pregnant'. A recorded pregnancy status may decide it only after clinical approval.",
    ),
)

# Fields read from PatientRiskProfile, with how each maps to a state.
PROFILE_FIELDS: tuple[str, ...] = (
    "smoking_status",
    "height_cm",
    "weight_kg",
    "bmi",
    "activity_minutes_per_week",
    "raised_lipids",
    "pregnancy_status",
    "family_diabetes",
    "family_heart_disease",
    "family_breast_cancer",
    "family_colorectal_cancer",
    "known_allergies",
    "family_cancer_history",
    "family_chronic_or_autoimmune_history",
    "known_genetic_findings",
)
RISK_FIELDS = frozenset(PROFILE_FIELDS)

FIRST_DEGREE = frozenset({"mother", "father", "sister", "brother", "half_sister", "half_brother", "daughter", "son"})
SECOND_DEGREE = frozenset(
    {
        "maternal_grandmother",
        "maternal_grandfather",
        "paternal_grandmother",
        "paternal_grandfather",
        "maternal_aunt",
        "maternal_uncle",
        "paternal_aunt",
        "paternal_uncle",
    }
)


def relationship_degree(relationship: str) -> Literal["first", "second", "other", "unknown"]:
    """Kinship degree by definition only. Half-siblings are grouped with first degree for display."""
    if relationship in FIRST_DEGREE:
        return "first"
    if relationship in SECOND_DEGREE:
        return "second"
    return "unknown" if relationship == "unknown" else "other"


@dataclass(frozen=True)
class RiskFact:
    field: str
    state: FactState
    value: str | float | int | None
    source: Verification
    # Rules that name this field, and whether an approved mapping lets them use it.
    rule_ids: tuple[str, ...] = ()
    actionable_rule_ids: tuple[str, ...] = ()
    detail: Mapping[str, object] = field(default_factory=dict)


def _yes_no_state(value: YesNoUnknown) -> FactState:
    return {YesNoUnknown.yes: "present", YesNoUnknown.no: "absent"}.get(value, "unknown")


def _profile_state(name: str, value: object) -> FactState:
    if value is None:
        return "unknown"
    if name == "smoking_status":
        if value == SmokingStatus.unknown:
            return "unknown"
        return "absent" if value == SmokingStatus.never else "present"
    if isinstance(value, YesNoUnknown):
        return _yes_no_state(value)
    return "value"


def bmi_of(profile: PatientRiskProfile | None) -> float | None:
    if profile and profile.height_cm and profile.weight_kg:
        return round(profile.weight_kg / (profile.height_cm / 100) ** 2, 1)
    return None


def _strongest_source(sources: Iterable[Verification]) -> Verification:
    sources = set(sources)
    if Verification.clinically_confirmed in sources:
        return Verification.clinically_confirmed
    if Verification.patient_reported in sources:
        return Verification.patient_reported
    return Verification.unknown


@dataclass(frozen=True)
class RiskContext:
    """Everything about a patient's risk factors that rule evaluation may see."""

    facts: Mapping[str, RiskFact]
    mappings: tuple[RiskInputMapping, ...] = RISK_INPUT_MAPPINGS

    def value(self, name: str) -> object:
        fact = self.facts.get(name)
        return fact.value if fact else None

    def state(self, name: str) -> FactState:
        fact = self.facts.get(name)
        return fact.state if fact else "unknown"

    def approved(self, rule_id: str, name: str) -> bool:
        return any(
            mapping.status == "approved" and mapping.field == name and rule_id in mapping.rule_ids for mapping in self.mappings
        )


EMPTY_RISK_CONTEXT = RiskContext(facts={})


def build_risk_context(
    profile: PatientRiskProfile | None,
    relatives: Sequence[FamilyRelative] = (),
    conditions: Sequence[FamilyCondition] = (),
    rule_fields: Mapping[str, Sequence[str]] | None = None,
    mappings: tuple[RiskInputMapping, ...] = RISK_INPUT_MAPPINGS,
) -> RiskContext:
    """rule_fields: rule id -> the input fields that rule names (see criteria.rule_input_fields)."""
    stored = profile or PatientRiskProfile(patient_id=0)
    source = stored.information_source if profile else Verification.unknown
    naming: dict[str, list[str]] = {}
    for rule_id, fields in (rule_fields or {}).items():
        for name in fields:
            naming.setdefault(name, []).append(rule_id)

    def make(name: str, state: FactState, value: object, fact_source: Verification, detail: Mapping[str, object] | None = None) -> RiskFact:
        rule_ids = tuple(sorted(naming.get(name, [])))
        actionable = tuple(
            rule_id
            for rule_id in rule_ids
            if any(m.status == "approved" and m.field == name and rule_id in m.rule_ids for m in mappings)
        )
        return RiskFact(name, state, value, fact_source, rule_ids, actionable, detail or {})

    facts: dict[str, RiskFact] = {}
    for name in PROFILE_FIELDS:
        value = bmi_of(profile) if name == "bmi" else getattr(stored, name)
        state = _profile_state(name, value)
        plain = value.value if hasattr(value, "value") else value
        facts[name] = make(name, state, plain, source if state != "unknown" else Verification.unknown)

    # Structured family history refines the summary flags. A record makes the
    # history present; it never turns an unknown flag into "absent".
    by_relative = {relative.id: relative for relative in relatives}
    for category, flag in (
        (FamilyConditionCategory.cancer, "family_cancer_history"),
        (None, "family_chronic_or_autoimmune_history"),
    ):
        matching = [
            condition
            for condition in conditions
            if (condition.category == category if category else condition.category != FamilyConditionCategory.cancer)
        ]
        if not matching:
            continue
        affected = {condition.relative_id for condition in matching}
        first = sum(
            1 for relative_id in affected if relationship_degree(by_relative[relative_id].relationship) == "first"
        ) if by_relative else 0
        facts[flag] = make(
            flag,
            "present",
            "yes",
            _strongest_source(condition.verification for condition in matching),
            {"affected_relatives": len(affected), "first_degree_relatives": first, "records": len(matching)},
        )
    return RiskContext(facts=facts, mappings=mappings)
