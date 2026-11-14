"""Allergies, structured family history and genetic findings.

Demo only: no authentication, synthetic data. These records are shown to the
patient and the clinician; none of them changes a screening status.
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import SessionDep
from app.medical_history import (
    condition_errors,
    flags_contradicted_by,
    load_history,
    medical_history_read,
    normalize_allergen,
    relative_read,
    vocabulary,
)
from app.models import Allergy, FamilyCondition, FamilyRelative, GeneticFinding, PatientRiskProfile, YesNoUnknown
from app.routers.profiles import get_patient_or_404
from app.routers.risk_profiles import risk_profile_read
from app.schemas import (
    AllergyCreate,
    AllergyRead,
    AllergyUpdate,
    FamilyConditionCreate,
    FamilyConditionRead,
    FamilyConditionUpdate,
    FamilyRelativeCreate,
    FamilyRelativeRead,
    FamilyRelativeUpdate,
    GeneticFindingCreate,
    GeneticFindingRead,
    GeneticFindingUpdate,
    MedicalHistoryRead,
    VocabularyRead,
)
from app.validation import raise_if_invalid

router = APIRouter(tags=["Medical history"])


def _owned_or_404(session: Session, model, item_id: int, patient_id: int, label: str):
    item = session.get(model, item_id)
    # Another patient's record reads as not found, so an id reveals nothing.
    if item is None or item.patient_id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{label} {item_id} not found for patient {patient_id}")
    return item


def _profile_says_no(session: Session, patient_id: int, flag: str) -> bool:
    profile = session.get(PatientRiskProfile, patient_id)
    return profile is not None and getattr(profile, flag) == YesNoUnknown.no


@router.get("/medical-history/vocabulary", response_model=VocabularyRead)
def read_vocabulary() -> VocabularyRead:
    return vocabulary()


@router.get(
    "/patients/{patient_id}/medical-history",
    response_model=MedicalHistoryRead,
    description="Risk factors, allergies, family and genetic history, with the state and source of each fact.",
)
def read_medical_history(patient_id: int, request: Request, session: SessionDep) -> MedicalHistoryRead:
    get_patient_or_404(session, patient_id)
    profile = risk_profile_read(patient_id, session.get(PatientRiskProfile, patient_id))
    return medical_history_read(session, patient_id, request.app.state.rule_set, profile)


# ---------------------------------------------------------------- allergies


@router.get("/patients/{patient_id}/allergies", response_model=list[AllergyRead])
def list_allergies(patient_id: int, session: SessionDep) -> list[Allergy]:
    get_patient_or_404(session, patient_id)
    return load_history(session, patient_id).allergies


@router.post("/patients/{patient_id}/allergies", response_model=AllergyRead, status_code=status.HTTP_201_CREATED)
def add_allergy(patient_id: int, body: AllergyCreate, session: SessionDep) -> Allergy:
    get_patient_or_404(session, patient_id)
    if _profile_says_no(session, patient_id, "known_allergies"):
        raise_if_invalid({"known_allergies": "known_allergies is recorded as 'no'. Change it before adding an allergy."})
    allergy = Allergy(patient_id=patient_id, allergen_key=normalize_allergen(body.allergen), **body.model_dump())
    session.add(allergy)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Patient {patient_id} already has '{body.allergen}'. Update that record instead.")
    session.refresh(allergy)
    return allergy


@router.patch("/patients/{patient_id}/allergies/{allergy_id}", response_model=AllergyRead)
def update_allergy(patient_id: int, allergy_id: int, body: AllergyUpdate, session: SessionDep) -> Allergy:
    get_patient_or_404(session, patient_id)
    allergy = _owned_or_404(session, Allergy, allergy_id, patient_id, "Allergy")
    changes = body.model_dump(exclude_unset=True)
    if "allergen" in changes:
        changes["allergen_key"] = normalize_allergen(changes["allergen"])
    allergy.sqlmodel_update(changes)
    session.add(allergy)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Another allergy record already has that allergen")
    session.refresh(allergy)
    return allergy


@router.delete("/patients/{patient_id}/allergies/{allergy_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_allergy(patient_id: int, allergy_id: int, session: SessionDep) -> None:
    get_patient_or_404(session, patient_id)
    session.delete(_owned_or_404(session, Allergy, allergy_id, patient_id, "Allergy"))
    session.commit()


# ---------------------------------------------------------------- family history


def _condition_checks(session: Session, patient_id: int, relative_id: int, body: FamilyConditionCreate, pending: list | None = None) -> None:
    raise_if_invalid(condition_errors(body.category, body.condition, body.condition_other))
    raise_if_invalid(flags_contradicted_by(body.category, body.condition, session.get(PatientRiskProfile, patient_id)))
    existing = list(session.exec(select(FamilyCondition).where(FamilyCondition.relative_id == relative_id)).all()) + (pending or [])
    if any((c.category, c.condition, c.condition_other) == (body.category, body.condition, body.condition_other) for c in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This relative already has that condition recorded")


@router.get("/patients/{patient_id}/family-history", response_model=list[FamilyRelativeRead])
def list_family_history(patient_id: int, session: SessionDep) -> list[FamilyRelativeRead]:
    get_patient_or_404(session, patient_id)
    records = load_history(session, patient_id)
    return [relative_read(relative, records.conditions) for relative in records.relatives]


@router.post(
    "/patients/{patient_id}/family-history/relatives",
    response_model=FamilyRelativeRead,
    status_code=status.HTTP_201_CREATED,
    description="Add one affected relative, optionally with their conditions. Add a second relative with the same relationship as a separate record.",
)
def add_relative(patient_id: int, body: FamilyRelativeCreate, session: SessionDep) -> FamilyRelativeRead:
    get_patient_or_404(session, patient_id)
    relative = FamilyRelative(patient_id=patient_id, relationship=body.relationship, label=body.label)
    session.add(relative)
    session.flush()
    added: list[FamilyCondition] = []
    try:
        for item in body.conditions:
            _condition_checks(session, patient_id, relative.id, item, added)
            added.append(FamilyCondition(patient_id=patient_id, relative_id=relative.id, **item.model_dump()))
    except HTTPException:
        session.rollback()
        raise
    session.add_all(added)
    session.commit()
    session.refresh(relative)
    return relative_read(relative, added)


@router.patch("/patients/{patient_id}/family-history/relatives/{relative_id}", response_model=FamilyRelativeRead)
def update_relative(patient_id: int, relative_id: int, body: FamilyRelativeUpdate, session: SessionDep) -> FamilyRelativeRead:
    get_patient_or_404(session, patient_id)
    relative = _owned_or_404(session, FamilyRelative, relative_id, patient_id, "Relative")
    relative.sqlmodel_update(body.model_dump(exclude_unset=True))
    session.add(relative)
    session.commit()
    session.refresh(relative)
    return relative_read(relative, load_history(session, patient_id).conditions)


@router.delete("/patients/{patient_id}/family-history/relatives/{relative_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_relative(patient_id: int, relative_id: int, session: SessionDep) -> None:
    get_patient_or_404(session, patient_id)
    relative = _owned_or_404(session, FamilyRelative, relative_id, patient_id, "Relative")
    for condition in session.exec(select(FamilyCondition).where(FamilyCondition.relative_id == relative.id)).all():
        session.delete(condition)
    session.delete(relative)
    session.commit()


@router.post(
    "/patients/{patient_id}/family-history/relatives/{relative_id}/conditions",
    response_model=FamilyConditionRead,
    status_code=status.HTTP_201_CREATED,
)
def add_condition(patient_id: int, relative_id: int, body: FamilyConditionCreate, session: SessionDep) -> FamilyCondition:
    get_patient_or_404(session, patient_id)
    _owned_or_404(session, FamilyRelative, relative_id, patient_id, "Relative")
    _condition_checks(session, patient_id, relative_id, body)
    condition = FamilyCondition(patient_id=patient_id, relative_id=relative_id, **body.model_dump())
    session.add(condition)
    session.commit()
    session.refresh(condition)
    return condition


@router.patch("/patients/{patient_id}/family-history/conditions/{condition_id}", response_model=FamilyConditionRead)
def update_condition(patient_id: int, condition_id: int, body: FamilyConditionUpdate, session: SessionDep) -> FamilyCondition:
    get_patient_or_404(session, patient_id)
    condition = _owned_or_404(session, FamilyCondition, condition_id, patient_id, "Family condition")
    condition.sqlmodel_update(body.model_dump(exclude_unset=True))
    session.add(condition)
    session.commit()
    session.refresh(condition)
    return condition


@router.delete("/patients/{patient_id}/family-history/conditions/{condition_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_condition(patient_id: int, condition_id: int, session: SessionDep) -> None:
    get_patient_or_404(session, patient_id)
    session.delete(_owned_or_404(session, FamilyCondition, condition_id, patient_id, "Family condition"))
    session.commit()


# ---------------------------------------------------------------- genetic findings


@router.get("/patients/{patient_id}/genetic-findings", response_model=list[GeneticFindingRead])
def list_genetic_findings(patient_id: int, session: SessionDep) -> list[GeneticFinding]:
    get_patient_or_404(session, patient_id)
    return load_history(session, patient_id).genetic


@router.post(
    "/patients/{patient_id}/genetic-findings",
    response_model=GeneticFindingRead,
    status_code=status.HTTP_201_CREATED,
    description="Recorded as reported. VITALA does not infer risk or screening from it, and does not assume it is confirmed.",
)
def add_genetic_finding(patient_id: int, body: GeneticFindingCreate, session: SessionDep) -> GeneticFinding:
    patient = get_patient_or_404(session, patient_id)
    if _profile_says_no(session, patient_id, "known_genetic_findings"):
        raise_if_invalid({"known_genetic_findings": "known_genetic_findings is recorded as 'no'. Change it before adding a finding."})
    _genetic_date_check(body.test_date, patient.date_of_birth)
    finding = GeneticFinding(patient_id=patient_id, **body.model_dump())
    session.add(finding)
    session.commit()
    session.refresh(finding)
    return finding


def _genetic_date_check(test_date, birth) -> None:
    from datetime import date

    if test_date and test_date > date.today():
        raise_if_invalid({"test_date": "Date cannot be in the future"})
    if test_date and birth and test_date < birth:
        raise_if_invalid({"test_date": "Date cannot be before the patient's date of birth"})


@router.patch("/patients/{patient_id}/genetic-findings/{finding_id}", response_model=GeneticFindingRead)
def update_genetic_finding(patient_id: int, finding_id: int, body: GeneticFindingUpdate, session: SessionDep) -> GeneticFinding:
    patient = get_patient_or_404(session, patient_id)
    finding = _owned_or_404(session, GeneticFinding, finding_id, patient_id, "Genetic finding")
    changes = body.model_dump(exclude_unset=True)
    _genetic_date_check(changes.get("test_date", finding.test_date), patient.date_of_birth)
    finding.sqlmodel_update(changes)
    session.add(finding)
    session.commit()
    session.refresh(finding)
    return finding


@router.delete("/patients/{patient_id}/genetic-findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_genetic_finding(patient_id: int, finding_id: int, session: SessionDep) -> None:
    get_patient_or_404(session, patient_id)
    session.delete(_owned_or_404(session, GeneticFinding, finding_id, patient_id, "Genetic finding"))
    session.commit()
