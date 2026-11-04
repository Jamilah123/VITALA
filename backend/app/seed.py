"""Add synthetic demo data to the development database.

Run from the backend folder: .\\.venv\\Scripts\\python.exe -m app.seed
It adds one synthetic patient and one synthetic demo clinic. Running it again
changes nothing, and it never edits or links records it did not create.
"""

from datetime import date, datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import Settings
from app.database import build_engine, init_db
from app.models import (
    Appointment,
    AppointmentStatus,
    BookingSource,
    Clinic,
    ClinicPatient,
    ConditionStatus,
    DiabetesType,
    Doctor,
    Patient,
    Sex,
)

SEED_KEY = "synthetic-patient-1"
DEMO_CLINIC_KEY = "demo-clinic"

DIAGNOSED, NOT_DIAGNOSED = ConditionStatus.diagnosed, ConditionStatus.not_diagnosed
# Riyadh has no daylight saving, so a fixed offset is exact for these demo times.
RIYADH = timezone(timedelta(hours=3))

# Invented values only. Names say they are synthetic so they cannot pass for real people.
DEMO_DOCTORS = [
    ("د. اسم تجريبي 1", "طب الأسرة"),
    ("د. اسم تجريبي 2", "الباطنة"),
    ("د. اسم تجريبي 3", "الغدد الصماء والسكري"),
]

DEMO_PATIENTS = [
    dict(date_of_birth=date(1979, 4, 2), sex=Sex.female, diabetes_status=DIAGNOSED, diabetes_type=DiabetesType.type_2, diabetes_diagnosis_date=date(2018, 9, 1)),
    dict(date_of_birth=date(1971, 11, 20), sex=Sex.male, diabetes_status=NOT_DIAGNOSED, hypertension_status=DIAGNOSED, hypertension_diagnosis_date=date(2016, 2, 14)),
    dict(date_of_birth=date(1988, 7, 9), sex=Sex.female),
    dict(date_of_birth=date(1965, 1, 30), sex=Sex.male, diabetes_status=DIAGNOSED, diabetes_type=DiabetesType.type_2, hypertension_status=DIAGNOSED),
    dict(sex=Sex.unknown, hypertension_status=NOT_DIAGNOSED),
]

# (doctor index, patient index, Riyadh time, status, booking source, visit reason)
DEMO_APPOINTMENTS = [
    (0, 0, datetime(2026, 10, 20, 9, 0, tzinfo=RIYADH), AppointmentStatus.completed, BookingSource.vitala, "متابعة دورية"),
    (1, 1, datetime(2026, 10, 27, 11, 30, tzinfo=RIYADH), AppointmentStatus.no_show, BookingSource.clinic, "مراجعة ضغط الدم"),
    (2, 3, datetime(2026, 11, 9, 9, 0, tzinfo=RIYADH), AppointmentStatus.scheduled, BookingSource.vitala, "متابعة السكري"),
    (0, 2, datetime(2026, 11, 9, 10, 30, tzinfo=RIYADH), AppointmentStatus.scheduled, BookingSource.clinic, "زيارة أولى"),
    (1, 1, datetime(2026, 11, 10, 13, 0, tzinfo=RIYADH), AppointmentStatus.scheduled, BookingSource.unknown, "مراجعة ضغط الدم"),
    (0, 4, datetime(2026, 11, 11, 8, 30, tzinfo=RIYADH), AppointmentStatus.cancelled, BookingSource.vitala, "زيارة أولى"),
    (2, 0, datetime(2026, 11, 12, 12, 0, tzinfo=RIYADH), AppointmentStatus.scheduled, BookingSource.vitala, "مراجعة نتائج"),
]


def seed_synthetic_patient(session: Session) -> tuple[Patient, bool]:
    """Return the synthetic patient, and whether this call created it."""
    existing = session.exec(select(Patient).where(Patient.seed_key == SEED_KEY)).first()
    if existing:
        return existing, False

    # Invented test values, not a real person. Hypertension stays unknown on
    # purpose, to show missing information rather than a negative finding.
    patient = Patient(
        seed_key=SEED_KEY,
        date_of_birth=date(1985, 3, 15),
        sex=Sex.female,
        diabetes_status=ConditionStatus.diagnosed,
        diabetes_type=DiabetesType.type_2,
        diabetes_diagnosis_date=date(2020, 6, 1),
    )
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient, True


def seed_demo_clinic(session: Session) -> tuple[Clinic, bool]:
    """Return the demo clinic, and whether this call created it. Created in one transaction."""
    existing = session.exec(select(Clinic).where(Clinic.seed_key == DEMO_CLINIC_KEY)).first()
    if existing:
        return existing, False

    clinic = Clinic(seed_key=DEMO_CLINIC_KEY, name_ar="عيادة Vitala التجريبية", city_ar="الرياض", is_demo=True)
    session.add(clinic)
    session.flush()

    doctors = [
        Doctor(seed_key=f"{DEMO_CLINIC_KEY}-doctor-{number}", clinic_id=clinic.id, name_ar=name, specialty_ar=specialty)
        for number, (name, specialty) in enumerate(DEMO_DOCTORS, start=1)
    ]
    patients = [
        Patient(seed_key=f"{DEMO_CLINIC_KEY}-patient-{number}", **fields) for number, fields in enumerate(DEMO_PATIENTS, start=1)
    ]
    session.add_all([*doctors, *patients])
    session.flush()

    links = [
        ClinicPatient(
            seed_key=f"{DEMO_CLINIC_KEY}-link-{number}",
            clinic_id=clinic.id,
            patient_id=patient.id,
            display_name_ar=f"مريض تجريبي {number}",
            file_number=f"DEMO-{number:04d}",
        )
        for number, patient in enumerate(patients, start=1)
    ]
    session.add_all(links)
    session.flush()

    session.add_all(
        Appointment(
            seed_key=f"{DEMO_CLINIC_KEY}-appointment-{number}",
            clinic_id=clinic.id,
            doctor_id=doctors[doctor].id,
            clinic_patient_id=links[patient].id,
            scheduled_at=scheduled_at,
            status=appointment_status,
            booking_source=source,
            visit_reason_ar=reason,
        )
        for number, (doctor, patient, scheduled_at, appointment_status, source, reason) in enumerate(DEMO_APPOINTMENTS, start=1)
    )
    session.commit()
    session.refresh(clinic)
    return clinic, True


def main() -> None:
    settings = Settings()
    engine = build_engine(settings.database_path)
    init_db(engine, settings.database_path)
    with Session(engine) as session:
        patient, created = seed_synthetic_patient(session)
        outcome = "Created" if created else "Already exists, nothing changed:"
        print(f"{outcome} synthetic patient id={patient.id} in {settings.database_path}")
        clinic, created = seed_demo_clinic(session)
        outcome = "Created" if created else "Already exists, nothing changed:"
        print(f"{outcome} demo clinic id={clinic.id} in {settings.database_path}")
    engine.dispose()


if __name__ == "__main__":
    main()
