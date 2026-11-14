"""Build the synthetic patient context the RAG service accepts, from backend records.

Privacy rules (enforced here and tested):
  * Only synthetic demo patients may be used: patients created by `python -m app.seed`
    (they have a seed_key, which the API can neither set nor change). Any other
    patient is refused until authentication, consent and a privacy review exist.
  * Data minimisation: age instead of date of birth; generic medication names;
    no names, file numbers, insurance, national ID, allergies or free-text notes.
  * The screening "plan" sent is the draft engine output, labelled as draft. It
    carries no status or due date, because VITALA calculates neither.
"""

from datetime import date

from sqlmodel import Session, select

from app.medical_history import load_history
from app.models import ConditionStatus, MedicationUse, Patient, ScreeningRecord, Sex
from app.risk_inputs import bmi_of
from app.rules import RuleSet
from app.schemas import ScreeningSummary
from app.screening import full_years

# Backend test ids -> test codes the RAG recognises (patient_context.TEST_CATALOG).
RAG_TEST_CODES = {
    "hba1c": "HBA1C",
    "fasting_glucose": "FPG",
    "blood_pressure": "BP",
    "lipid_profile": "LIPID",
    "egfr": "EGFR",
    "uacr": "UACR",
    "eye_exam": "EYE",
}

DRAFT_REASON = {
    "en": "Draft rule candidate from VITALA's unreviewed screening engine, for clinician review. Not a recommendation.",
    "ar": "مرشح من قاعدة مسودة في محرك الفحوصات لم يراجعها طبيب، للمراجعة السريرية فقط. ليس توصية.",
}


class PatientContextNotAllowed(Exception):
    """The patient is not a synthetic demo patient."""


def synthetic_id(patient: Patient) -> str:
    return f"SYN-VITALA-P{patient.id}"


def is_synthetic(patient: Patient) -> bool:
    return patient.seed_key is not None


def require_synthetic(patient: Patient) -> None:
    if not is_synthetic(patient):
        raise PatientContextNotAllowed()


def _conditions(patient: Patient) -> list[dict]:
    history = []
    if patient.diabetes_status == ConditionStatus.diagnosed:
        name = {"type_1": "Type 1 diabetes", "type_2": "Type 2 diabetes"}.get(patient.diabetes_type, "Diabetes")
        history.append({"condition": name, "since": patient.diabetes_diagnosis_date.isoformat() if patient.diabetes_diagnosis_date else None, "status": "diagnosed"})
    if patient.hypertension_status == ConditionStatus.diagnosed:
        since = patient.hypertension_diagnosis_date
        history.append({"condition": "Hypertension", "since": since.isoformat() if since else None, "status": "diagnosed"})
    for condition, status in (("Diabetes", patient.diabetes_status), ("Hypertension", patient.hypertension_status)):
        if status == ConditionStatus.not_diagnosed:
            history.append({"condition": condition, "status": "not diagnosed"})
    return history


def _result(record: ScreeningRecord) -> dict:
    # Callers only pass records that have a result; nothing is filled in.
    return {
        "code": RAG_TEST_CODES.get(record.test_id),
        "test": record.test_name,
        "value": record.result,
        "unit": record.unit or "",
        "date": record.completed_on.isoformat(),
        "source": record.source.value,
    }


def build_patient_context(
    session: Session,
    patient: Patient,
    rule_set: RuleSet,
    catalogue: dict,
    today: date,
    summary: ScreeningSummary | None = None,
    only_record: ScreeningRecord | None = None,
) -> tuple[dict, list[str]]:
    """Return the context and the names of the sections it contains."""
    require_synthetic(patient)
    ctx: dict = {"is_synthetic": True, "patient_id": synthetic_id(patient), "label": "VITALA synthetic demo patient", "data_as_of": today.isoformat()}
    if patient.date_of_birth:
        ctx["age"] = full_years(patient.date_of_birth, today)
    if patient.sex != Sex.unknown:
        ctx["sex"] = patient.sex.value
    ctx["medical_history"] = _conditions(patient)

    uses = session.exec(select(MedicationUse).where(MedicationUse.patient_id == patient.id)).all()
    medications = []
    for use in uses:
        entry = catalogue.get(use.medication_id)
        if entry is None or entry.status != "active":
            continue  # archived entries are outside the chatbot's medication scope
        medications.append({"name": entry.generic_name, "since": use.start_date.isoformat() if use.start_date else None})
    ctx["medications"] = medications

    records = load_history(session, patient.id)
    profile = records.profile
    if profile is not None:
        bmi = bmi_of(profile)
        if profile.height_cm:
            ctx["height_cm"] = profile.height_cm
        if profile.weight_kg:
            ctx["weight_kg"] = profile.weight_kg
        if bmi:
            ctx["bmi"] = bmi
        factors = []
        if profile.smoking_status in ("current", "former"):
            factors.append({"factor": f"Smoking: {profile.smoking_status.value} (as recorded)"})
        if profile.raised_lipids == "yes":
            factors.append({"factor": "High cholesterol history (as recorded)"})
        if profile.activity_minutes_per_week is not None:
            factors.append({"factor": f"Physical activity: {profile.activity_minutes_per_week} minutes per week (as recorded)"})
        ctx["risk_factors"] = factors

    by_id = {relative.id: relative for relative in records.relatives}
    family = [
        {
            "condition": condition.condition_other or condition.condition.replace("_", " "),
            "relative": by_id[condition.relative_id].relationship.value.replace("_", " "),
            "status": condition.verification.value.replace("_", " "),
        }
        for condition in records.conditions
    ]
    if profile is not None:
        for flag, label in (("family_diabetes", "diabetes"), ("family_heart_disease", "heart disease")):
            if getattr(profile, flag) == "yes" and not any(label in item["condition"] for item in family):
                family.append({"condition": label, "status": "reported (relative not recorded)"})
    ctx["family_history"] = family

    if only_record is not None:
        # Analyze with VITALA: exactly one result, and no plan, so nothing else is discussed.
        ctx["previous_results"] = [_result(only_record)]
    else:
        stored = session.exec(select(ScreeningRecord).where(ScreeningRecord.patient_id == patient.id)).all()
        ctx["previous_results"] = [_result(record) for record in stored if record.result]
        if summary is not None:
            plan = []
            for test in summary.tests:
                rule_ids = test.candidate_rule_ids or test.needs_information_rule_ids
                if not rule_ids:
                    continue
                plan.append(
                    {
                        "name": test.test_id.replace("_", " "),
                        "name_ar": test.name_ar,
                        "code": RAG_TEST_CODES.get(test.test_id),
                        "reason": DRAFT_REASON["en"],
                        "reason_ar": DRAFT_REASON["ar"],
                        "rule_id": ",".join(rule_ids),
                    }
                )
            ctx["screening_plan"] = plan
    return ctx, sorted(key for key in ctx if key not in ("is_synthetic", "patient_id", "label", "data_as_of"))
