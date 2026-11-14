from collections.abc import Iterable
from dataclasses import dataclass

from app.models import ConditionStatus, DiabetesType
from app.rules import Rule

DIAGNOSED = ConditionStatus.diagnosed
NOT_DIAGNOSED = ConditionStatus.not_diagnosed
TYPE_1 = DiabetesType.type_1
TYPE_2 = DiabetesType.type_2

INPUT_ALIASES = {"diabetes_diagnosed": "diabetes_status", "hypertension_diagnosed": "hypertension_status"}


@dataclass(frozen=True)
class Criteria:
    # Conditions read from each rule's eligibility_ar. Like the rules, this
    # reading has not been reviewed by a clinician.
    diabetes: ConditionStatus | None = None
    diabetes_types: tuple[DiabetesType, ...] = ()
    type_1_min_years: int | None = None
    min_age: int | None = None
    # Eligibility requires this fact to be on record. Its value is not judged.
    on_record: tuple[str, ...] = ()
    # Eligibility depends on the value of these, which VITALA does not record yet.
    uncollected: tuple[str, ...] = ()
    # Eligibility depends on a recorded risk factor having this value. It is applied
    # only when an approved RiskInputMapping (risk_inputs.py) covers the rule and
    # field; until then the field leaves the rule undecided, as if uncollected.
    risk_required: tuple[tuple[str, str], ...] = ()


CLINICIAN_DECIDES_NEED = Criteria(uncollected=("clinician_next_due_date",))

CRITERIA: dict[str, Criteria] = {
    "DM01": Criteria(uncollected=("hba1c_at_individual_target",)),
    "DM02": Criteria(uncollected=("hba1c_at_individual_target",)),
    "DM03": Criteria(diabetes_types=(TYPE_1, TYPE_2), type_1_min_years=5),
    "DM04": Criteria(diabetes_types=(TYPE_1, TYPE_2), type_1_min_years=5),
    "DM05": Criteria(diabetes_types=(TYPE_2,)),
    "DM06": Criteria(diabetes_types=(TYPE_1,)),
    "DM07": Criteria(on_record=("last_eye_exam_date",)),
    "DM08": Criteria(),
    "DM09": Criteria(),
    "DM10": Criteria(diabetes_types=(TYPE_1, TYPE_2)),
    "HTN01": Criteria(uncollected=("bp_control_status", "stable_since")),
    "HTN02": Criteria(uncollected=("medication_change_date",)),
    "HTN03": Criteria(min_age=18, risk_required=(("pregnancy_status", "no"),)),
    "HTN04": CLINICIAN_DECIDES_NEED,
    "HTN05": CLINICIAN_DECIDES_NEED,
    "HTN06": CLINICIAN_DECIDES_NEED,
    "HTN07": CLINICIAN_DECIDES_NEED,
    "HTN08": CLINICIAN_DECIDES_NEED,
    "HTN09": CLINICIAN_DECIDES_NEED,
    "MED01": Criteria(),
    "MED02": Criteria(),
    "MED03": Criteria(diabetes=DIAGNOSED),
    "MED04": Criteria(diabetes=DIAGNOSED),
    "MED05": Criteria(diabetes=NOT_DIAGNOSED),
    "MED06": Criteria(),
    "MED07": Criteria(diabetes=DIAGNOSED, uncollected=("medication_start_or_change_date",)),
    "MED08": Criteria(diabetes=DIAGNOSED),
    "MED09": Criteria(uncollected=("planned_start_or_dose_increase",)),
    "MED10": Criteria(uncollected=("muscle_symptoms",)),
    "MED11": Criteria(uncollected=("inr_stability_since", "dose_stability_since")),
    "MED12": Criteria(uncollected=("clinical_stability",)),
    "MED13": Criteria(uncollected=("change_type", "change_date")),
    "MED14": Criteria(uncollected=("medication_indication",)),
}


def check_criteria_cover(rules: Iterable[Rule]) -> None:
    rule_ids = {rule.id for rule in rules}
    if rule_ids != CRITERIA.keys():
        raise ValueError(
            f"Eligibility criteria do not match the rule files. Rules without criteria: "
            f"{sorted(rule_ids - CRITERIA.keys())}. Criteria without rules: {sorted(CRITERIA.keys() - rule_ids)}"
        )


def rule_input_fields(rule: Rule) -> list[str]:
    criteria = CRITERIA[rule.id]
    inputs = [INPUT_ALIASES.get(field, field) for field in rule.required_inputs]
    risk = [name for name, _ in criteria.risk_required]
    return list(dict.fromkeys([*inputs, *criteria.on_record, *criteria.uncollected, *risk]))
