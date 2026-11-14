from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, select

from app.database import SessionDep
from app.models import MedicationUse, Patient, PatientRiskProfile, ScreeningRecord
from app.schemas import PatientCreate, PatientRead, PatientUpdate
from app.validation import birth_date_conflict, pregnancy_conflict, profile_errors, raise_if_invalid

router = APIRouter(prefix="/patients", tags=["Patient profiles"])


def get_patient_or_404(session: Session, patient_id: int) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Patient {patient_id} not found")
    return patient


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(body: PatientCreate, session: SessionDep) -> Patient:
    raise_if_invalid(profile_errors(body.model_dump()))
    patient = Patient(**body.model_dump())
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient


@router.get("/{patient_id}", response_model=PatientRead)
def read_patient(patient_id: int, session: SessionDep) -> Patient:
    return get_patient_or_404(session, patient_id)


@router.patch("/{patient_id}", response_model=PatientRead)
def update_patient(patient_id: int, body: PatientUpdate, session: SessionDep) -> Patient:
    patient = get_patient_or_404(session, patient_id)
    changes = body.model_dump(exclude_unset=True)
    merged = patient.model_dump() | changes
    raise_if_invalid(profile_errors(merged))
    uses = session.exec(select(MedicationUse).where(MedicationUse.patient_id == patient_id)).all()
    records = session.exec(select(ScreeningRecord).where(ScreeningRecord.patient_id == patient_id)).all()
    raise_if_invalid(birth_date_conflict(merged["date_of_birth"], uses, records))
    risk = session.get(PatientRiskProfile, patient_id)
    if risk:
        raise_if_invalid(pregnancy_conflict(merged["sex"], risk.pregnancy_status, "sex"))

    patient.sqlmodel_update(changes)
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient
