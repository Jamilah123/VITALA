from datetime import date

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import SessionDep
from app.models import Appointment, Clinic, ClinicPatient, Doctor, MedicationUse, Patient, PatientRiskProfile
from app.routers.risk_profiles import risk_profile_read
from app.routers.screening_records import list_records
from app.schemas import (
    AppointmentDetail,
    AppointmentRead,
    ClinicPatientRead,
    ClinicRead,
    DoctorRead,
    PatientRead,
    PreAppointmentSummary,
    SummaryMedication,
)
from app.screening import summarize_screening

router = APIRouter(prefix="/clinics", tags=["Clinics"])


def get_clinic_or_404(session: Session, clinic_id: int) -> Clinic:
    clinic = session.get(Clinic, clinic_id)
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Clinic {clinic_id} not found")
    return clinic


def clinic_patient_read(link: ClinicPatient, patient: Patient) -> ClinicPatientRead:
    return ClinicPatientRead(
        id=link.id,
        clinic_id=link.clinic_id,
        display_name_ar=link.display_name_ar,
        file_number=link.file_number,
        patient=PatientRead.model_validate(patient, from_attributes=True),
    )


def appointment_detail(session: Session, clinic_id: int, appointment_id: int) -> tuple[AppointmentDetail, Patient]:
    get_clinic_or_404(session, clinic_id)
    appointment = session.get(Appointment, appointment_id)
    link = session.get(ClinicPatient, appointment.clinic_patient_id) if appointment else None
    doctor = session.get(Doctor, appointment.doctor_id) if appointment else None
    # Every part must belong to this clinic. A mismatch reads as not found, so an
    # id from another clinic reveals nothing about it.
    if not (appointment and link and doctor) or {appointment.clinic_id, link.clinic_id, doctor.clinic_id} != {clinic_id}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Appointment {appointment_id} not found in clinic {clinic_id}")
    patient = session.get(Patient, link.patient_id)
    detail = AppointmentDetail(
        appointment=AppointmentRead.model_validate(appointment, from_attributes=True),
        doctor=DoctorRead.model_validate(doctor, from_attributes=True),
        patient=clinic_patient_read(link, patient),
    )
    return detail, patient


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
    return [clinic_patient_read(link, patient) for link, patient in rows]


@router.get("/{clinic_id}/appointments", response_model=list[AppointmentRead])
def list_appointments(clinic_id: int, session: SessionDep) -> list[Appointment]:
    get_clinic_or_404(session, clinic_id)
    query = select(Appointment).where(Appointment.clinic_id == clinic_id).order_by(Appointment.scheduled_at, Appointment.id)
    return list(session.exec(query).all())


@router.get("/{clinic_id}/appointments/{appointment_id}", response_model=AppointmentDetail)
def read_appointment(clinic_id: int, appointment_id: int, session: SessionDep) -> AppointmentDetail:
    return appointment_detail(session, clinic_id, appointment_id)[0]


@router.get(
    "/{clinic_id}/appointments/{appointment_id}/summary",
    response_model=PreAppointmentSummary,
    description="Read-only pre-appointment summary for the appointment's linked patient. Screening content is draft.",
)
def read_pre_appointment_summary(clinic_id: int, appointment_id: int, request: Request, session: SessionDep) -> PreAppointmentSummary:
    clinic = get_clinic_or_404(session, clinic_id)
    detail, patient = appointment_detail(session, clinic_id, appointment_id)
    uses = session.exec(select(MedicationUse).where(MedicationUse.patient_id == patient.id).order_by(MedicationUse.id)).all()
    catalogue = request.app.state.catalogue

    medications = []
    for use in uses:
        entry = catalogue.get(use.medication_id)
        medications.append(
            SummaryMedication(
                id=use.id,
                medication_id=use.medication_id,
                name_ar=entry.name_ar if entry else None,
                generic_name=entry.generic_name if entry else None,
                drug_class=entry.drug_class if entry else None,
                dose_text=use.dose_text,
                start_date=use.start_date,
                last_dose_change_date=use.last_dose_change_date,
            )
        )

    return PreAppointmentSummary(
        clinic=ClinicRead.model_validate(clinic, from_attributes=True),
        visit=detail,
        risk_profile=risk_profile_read(patient.id, session.get(PatientRiskProfile, patient.id)),
        medications=medications,
        screening=summarize_screening(request.app.state.rule_set, patient, uses, list_records(session, patient.id), date.today()),
    )
