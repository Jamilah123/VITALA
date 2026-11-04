from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session, select

from app.database import SessionDep
from app.models import Appointment, Clinic, ClinicPatient, Doctor, Patient
from app.schemas import AppointmentRead, ClinicPatientRead, ClinicRead, DoctorRead, PatientRead

router = APIRouter(prefix="/clinics", tags=["Clinics"])


def get_clinic_or_404(session: Session, clinic_id: int) -> Clinic:
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Clinic {clinic_id} not found")
    return clinic


@router.get("", response_model=list[ClinicRead])
def list_clinics(session: SessionDep) -> list[Clinic]:
    return list(session.exec(select(Clinic).order_by(Clinic.id)).all())


@router.get("/{clinic_id}", response_model=ClinicRead)
def read_clinic(clinic_id: int, session: SessionDep) -> Clinic:
    return get_clinic_or_404(session, clinic_id)


@router.get("/{clinic_id}/doctors", response_model=list[DoctorRead])
def list_doctors(clinic_id: int, session: SessionDep) -> list[Doctor]:
    get_clinic_or_404(session, clinic_id)
    return list(session.exec(select(Doctor).where(Doctor.clinic_id == clinic_id).order_by(Doctor.id)).all())


@router.get("/{clinic_id}/patients", response_model=list[ClinicPatientRead])
def list_clinic_patients(clinic_id: int, session: SessionDep) -> list[ClinicPatientRead]:
    get_clinic_or_404(session, clinic_id)
    rows = session.exec(
        select(ClinicPatient, Patient)
        .join(Patient, ClinicPatient.patient_id == Patient.id)
        .where(ClinicPatient.clinic_id == clinic_id)
        .order_by(ClinicPatient.id)
    ).all()
    return [
        ClinicPatientRead(
            id=link.id,
            clinic_id=link.clinic_id,
            display_name_ar=link.display_name_ar,
            file_number=link.file_number,
            patient=PatientRead.model_validate(patient, from_attributes=True),
        )
        for link, patient in rows
    ]


@router.get("/{clinic_id}/appointments", response_model=list[AppointmentRead])
def list_appointments(clinic_id: int, session: SessionDep) -> list[Appointment]:
    get_clinic_or_404(session, clinic_id)
    query = select(Appointment).where(Appointment.clinic_id == clinic_id).order_by(Appointment.scheduled_at, Appointment.id)
    return list(session.exec(query).all())
