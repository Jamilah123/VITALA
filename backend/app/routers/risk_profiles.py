from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.database import SessionDep
from app.models import PatientRiskProfile
from app.routers.profiles import get_patient_or_404
from app.schemas import RiskProfileCreate, RiskProfileRead, RiskProfileUpdate
from app.validation import pregnancy_conflict, raise_if_invalid

router = APIRouter(prefix="/patients/{patient_id}/risk-profile", tags=["Risk factors"])


def risk_profile_read(patient_id: int, profile: PatientRiskProfile | None) -> RiskProfileRead:
    stored = profile is not None
    profile = profile or PatientRiskProfile(patient_id=patient_id)
    bmi = None
    if profile.height_cm and profile.weight_kg:
        bmi = round(profile.weight_kg / (profile.height_cm / 100) ** 2, 1)
    return RiskProfileRead(stored=stored, bmi=bmi, **profile.model_dump())


@router.get("", response_model=RiskProfileRead)
def read_risk_profile(patient_id: int, session: SessionDep) -> RiskProfileRead:
    get_patient_or_404(session, patient_id)
    return risk_profile_read(patient_id, session.get(PatientRiskProfile, patient_id))


@router.post("", response_model=RiskProfileRead, status_code=status.HTTP_201_CREATED)
def create_risk_profile(patient_id: int, body: RiskProfileCreate, session: SessionDep) -> RiskProfileRead:
    patient = get_patient_or_404(session, patient_id)
    raise_if_invalid(pregnancy_conflict(patient.sex, body.pregnancy_status, "pregnancy_status"))

    profile = PatientRiskProfile(patient_id=patient_id, **body.model_dump())
    session.add(profile)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Patient {patient_id} already has a risk profile. Update it instead.",
        )
    session.refresh(profile)
    return risk_profile_read(patient_id, profile)


@router.patch("", response_model=RiskProfileRead)
def update_risk_profile(patient_id: int, body: RiskProfileUpdate, session: SessionDep) -> RiskProfileRead:
    patient = get_patient_or_404(session, patient_id)
    profile = session.get(PatientRiskProfile, patient_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Patient {patient_id} has no risk profile yet. Create it first.")
    changes = body.model_dump(exclude_unset=True)
    merged = profile.model_dump() | changes
    raise_if_invalid(pregnancy_conflict(patient.sex, merged["pregnancy_status"], "pregnancy_status"))

    profile.sqlmodel_update(changes)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return risk_profile_read(patient_id, profile)
