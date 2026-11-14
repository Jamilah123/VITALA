from datetime import date

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import SessionDep
from app.medical_history import medical_history_read, patient_risk_context
from app.routers.insurance import insurance_summary
from app.virtual_care import VirtualCareNotConfigured
from app.models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    BookingSource,
    Clinic,
    ClinicPatient,
    Doctor,
    MedicationUse,
    Patient,
    PatientRiskProfile,
    RecordSource,
    ScreeningRecord,
)
from app.routers.risk_profiles import risk_profile_read
from app.routers.screening_records import create_record, list_records
from app.schemas import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentRead,
    AppointmentStatusChange,
    AppointmentUpdate,
    ClinicScreeningRecordCreate,
    ClinicPatientRead,
    ClinicRead,
    DoctorRead,
    PatientRead,
    PreAppointmentSummary,
    ScreeningRecordRead,
    SummaryMedication,
)
from app.screening import summarize_screening
from app.validation import (
    appointment_time_errors,
    doctor_conflict_errors,
    raise_if_invalid,
    status_change_errors,
    utc_now,
)

router = APIRouter(prefix="/clinics", tags=["Clinics"])

DEMO_WRITE_NOTE = "Demo only: no authentication, synthetic data. clinic_id in the path is not an access control."


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
                catalogue_status=entry.status if entry else None,
            )
        )

    rule_set = request.app.state.rule_set
    risk_profile = risk_profile_read(patient.id, session.get(PatientRiskProfile, patient.id))
    risk = patient_risk_context(session, patient.id, rule_set)
    return PreAppointmentSummary(
        clinic=ClinicRead.model_validate(clinic, from_attributes=True),
        visit=detail,
        risk_profile=risk_profile,
        medications=medications,
        screening=summarize_screening(rule_set, patient, uses, list_records(session, patient.id), date.today(), risk=risk),
        medical_history=medical_history_read(session, patient.id, rule_set, risk_profile),
        insurance=insurance_summary(session, patient.id),
    )


@router.get(
    "/{clinic_id}/appointments/{appointment_id}/virtual-session",
    responses={409: {"description": "The appointment is in person"}, 501: {"description": "Video visits are not implemented"}},
    description="Extension point for in-app video visits. Not implemented: always 501 for virtual appointments.",
)
def read_virtual_session(clinic_id: int, appointment_id: int, request: Request, session: SessionDep) -> None:
    appointment = clinic_appointment(session, clinic_id, appointment_id)
    if appointment.appointment_type != AppointmentType.virtual:
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "not_virtual", "message": "This appointment is in person."})
    try:
        request.app.state.virtual_care.create_session(appointment.id)
    except VirtualCareNotConfigured:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            detail={"code": "virtual_care_not_implemented", "message": "In-app video visits are not available yet. Contact the clinic for the visit link."},
        )


def ownership_errors(session: Session, clinic_id: int, doctor_id: int | None = None, link_id: int | None = None) -> dict[str, str]:
    errors: dict[str, str] = {}
    if link_id is not None:
        link = session.get(ClinicPatient, link_id)
        if link is None or link.clinic_id != clinic_id:
            errors["clinic_patient_id"] = "Patient is not registered with this clinic"
    if doctor_id is not None:
        doctor = session.get(Doctor, doctor_id)
        if doctor is None or doctor.clinic_id != clinic_id:
            errors["doctor_id"] = "Doctor does not belong to this clinic"
    return errors


def doctor_times(session: Session, doctor_id: int, exclude_id: int | None = None) -> list:
    query = select(Appointment.scheduled_at).where(Appointment.doctor_id == doctor_id, Appointment.status == AppointmentStatus.scheduled)
    if exclude_id is not None:
        query = query.where(Appointment.id != exclude_id)
    return list(session.exec(query).all())


def clinic_appointment(session: Session, clinic_id: int, appointment_id: int) -> Appointment:
    appointment_detail(session, clinic_id, appointment_id)
    return session.get(Appointment, appointment_id)


@router.post(
    "/{clinic_id}/appointments",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    description=DEMO_WRITE_NOTE,
)
def create_appointment(clinic_id: int, body: AppointmentCreate, session: SessionDep) -> Appointment:
    get_clinic_or_404(session, clinic_id)
    errors = ownership_errors(session, clinic_id, doctor_id=body.doctor_id, link_id=body.clinic_patient_id)
    raise_if_invalid(errors | appointment_time_errors(body.scheduled_at, utc_now()))
    raise_if_invalid(doctor_conflict_errors(body.scheduled_at, doctor_times(session, body.doctor_id)))

    appointment = Appointment(
        clinic_id=clinic_id,
        status=AppointmentStatus.scheduled,
        booking_source=BookingSource.clinic,
        **body.model_dump(),
    )
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return appointment


@router.patch("/{clinic_id}/appointments/{appointment_id}", response_model=AppointmentRead, description=DEMO_WRITE_NOTE)
def update_appointment(clinic_id: int, appointment_id: int, body: AppointmentUpdate, session: SessionDep) -> Appointment:
    appointment = clinic_appointment(session, clinic_id, appointment_id)
    if appointment.status != AppointmentStatus.scheduled:
        raise_if_invalid({"status": "Only scheduled appointments can be changed"})
    changes = body.model_dump(exclude_unset=True)

    errors = ownership_errors(session, clinic_id, doctor_id=changes["doctor_id"]) if "doctor_id" in changes else {}
    if "scheduled_at" in changes:
        errors |= appointment_time_errors(changes["scheduled_at"], utc_now())
    raise_if_invalid(errors)
    if "doctor_id" in changes or "scheduled_at" in changes:
        doctor_id = changes.get("doctor_id", appointment.doctor_id)
        scheduled_at = changes.get("scheduled_at", appointment.scheduled_at)
        raise_if_invalid(doctor_conflict_errors(scheduled_at, doctor_times(session, doctor_id, exclude_id=appointment.id)))

    appointment.sqlmodel_update(changes)
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return appointment


@router.post("/{clinic_id}/appointments/{appointment_id}/status", response_model=AppointmentRead, description=DEMO_WRITE_NOTE)
def change_appointment_status(clinic_id: int, appointment_id: int, body: AppointmentStatusChange, session: SessionDep) -> Appointment:
    appointment = clinic_appointment(session, clinic_id, appointment_id)
    new_status = AppointmentStatus(body.status)
    raise_if_invalid(status_change_errors(appointment.status, new_status, appointment.scheduled_at, utc_now()))

    appointment.status = new_status
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return appointment


def clinic_link_or_404(session: Session, clinic_id: int, link_id: int) -> tuple[ClinicPatient, Patient]:
    get_clinic_or_404(session, clinic_id)
    link = session.get(ClinicPatient, link_id)
    # A link from another clinic reads as not found, so it reveals nothing.
    if link is None or link.clinic_id != clinic_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Patient {link_id} not found in clinic {clinic_id}")
    return link, session.get(Patient, link.patient_id)


@router.get("/{clinic_id}/patients/{link_id}", response_model=ClinicPatientRead)
def read_clinic_patient(clinic_id: int, link_id: int, session: SessionDep) -> ClinicPatientRead:
    return clinic_patient_read(*clinic_link_or_404(session, clinic_id, link_id))


@router.get("/{clinic_id}/patients/{link_id}/screening-records", response_model=list[ScreeningRecordRead])
def list_clinic_patient_records(clinic_id: int, link_id: int, session: SessionDep) -> list[ScreeningRecord]:
    _, patient = clinic_link_or_404(session, clinic_id, link_id)
    return list_records(session, patient.id)


@router.post(
    "/{clinic_id}/patients/{link_id}/screening-records",
    response_model=ScreeningRecordRead,
    status_code=status.HTTP_201_CREATED,
    description=f"Records a result as clinician_entered for the linked patient. {DEMO_WRITE_NOTE}",
)
def add_clinic_patient_record(clinic_id: int, link_id: int, body: ClinicScreeningRecordCreate, session: SessionDep) -> ScreeningRecord:
    _, patient = clinic_link_or_404(session, clinic_id, link_id)
    fields = body.model_dump() | {"source": RecordSource.clinician_entered}
    # An identical record is almost always a repeated submission. Records that differ
    # in any field, including several on one day, are still allowed.
    for existing in list_records(session, patient.id):
        if all(getattr(existing, name) == value for name, value in fields.items()):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"An identical record already exists for this patient (record {existing.id})",
            )
    return create_record(session, patient, fields)
