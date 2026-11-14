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
    AllergenCategory,
    Allergy,
    AllergySeverity,
    Appointment,
    AppointmentStatus,
    AppointmentType,
    BookingSource,
    Clinic,
    ClinicPatient,
    ConditionStatus,
    DiabetesType,
    Doctor,
    FamilyCondition,
    FamilyConditionCategory,
    FamilyRelationship,
    FamilyRelative,
    MedicationUse,
    Patient,
    PatientRiskProfile,
    RecordSource,
    ScreeningRecord,
    Sex,
    SmokingStatus,
    Verification,
    YesNoUnknown,
)

SEED_KEY = "synthetic-patient-1"
HISTORY_DEMO_KEY = "synthetic-patient-history-demo"
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


def seed_history_demo(session: Session, clinic: Clinic) -> tuple[Patient, bool]:
    """One synthetic patient with medications, risk factors, family history, allergies and results.

    Everything is created in one transaction, only when this seed's patient does not exist yet.
    Values are invented for demonstration and are not clinical examples to follow.
    """
    existing = session.exec(select(Patient).where(Patient.seed_key == HISTORY_DEMO_KEY)).first()
    if existing:
        return existing, False

    yes, no, unknown = YesNoUnknown.yes, YesNoUnknown.no, YesNoUnknown.unknown
    reported, confirmed = Verification.patient_reported, Verification.clinically_confirmed
    patient = Patient(
        seed_key=HISTORY_DEMO_KEY,
        date_of_birth=date(1972, 5, 10),
        sex=Sex.female,
        diabetes_status=DIAGNOSED,
        diabetes_type=DiabetesType.type_2,
        diabetes_diagnosis_date=date(2015, 3, 1),
        hypertension_status=DIAGNOSED,
        hypertension_diagnosis_date=date(2019, 1, 15),
    )
    session.add(patient)
    session.flush()
    session.add_all(
        [
            MedicationUse(patient_id=patient.id, medication_id="metformin", dose_text="1000 mg twice daily (synthetic)", start_date=date(2015, 4, 1)),
            MedicationUse(patient_id=patient.id, medication_id="lisinopril", dose_text="10 mg once daily (synthetic)", start_date=date(2019, 2, 1)),
            PatientRiskProfile(
                patient_id=patient.id,
                smoking_status=SmokingStatus.former,
                height_cm=160.0,
                weight_kg=78.0,
                activity_minutes_per_week=60,
                raised_lipids=yes,
                pregnancy_status=no,
                family_diabetes=yes,
                family_heart_disease=unknown,
                family_breast_cancer=yes,
                family_colorectal_cancer=no,
                information_source=reported,
                known_allergies=yes,
                family_cancer_history=yes,
                family_chronic_or_autoimmune_history=yes,
                known_genetic_findings=unknown,
            ),
            Allergy(patient_id=patient.id, allergen="Penicillin", allergen_key="penicillin", category=AllergenCategory.drug, reaction="Skin rash", severity=AllergySeverity.moderate, verification=reported),
        ]
    )
    mother = FamilyRelative(patient_id=patient.id, relationship=FamilyRelationship.mother)
    sister = FamilyRelative(patient_id=patient.id, relationship=FamilyRelationship.sister, label="older sister")
    session.add_all([mother, sister])
    session.flush()
    session.add_all(
        [
            FamilyCondition(patient_id=patient.id, relative_id=mother.id, category=FamilyConditionCategory.chronic, condition="type_2_diabetes", age_at_diagnosis=55, verification=reported),
            FamilyCondition(patient_id=patient.id, relative_id=mother.id, category=FamilyConditionCategory.cancer, condition="breast", age_at_diagnosis=62, verification=reported),
            FamilyCondition(patient_id=patient.id, relative_id=sister.id, category=FamilyConditionCategory.cancer, condition="breast", age_at_diagnosis=48, verification=confirmed),
            ScreeningRecord(patient_id=patient.id, test_id="hba1c", test_name="HbA1c", completed_on=date(2026, 8, 10), result="7.4", unit="%", reference_range="4.0-5.6 % (synthetic lab range)", source=RecordSource.lab_report),
            ScreeningRecord(patient_id=patient.id, test_id="egfr", test_name="eGFR", completed_on=date(2026, 8, 10), result="78", unit="mL/min/1.73m2", reference_range=">60 (synthetic lab range)", source=RecordSource.lab_report),
            ScreeningRecord(patient_id=patient.id, test_id="vitamin_b12", test_name="Vitamin B12", completed_on=date(2026, 2, 3), result="310", unit="pg/mL", source=RecordSource.patient_reported),
        ]
    )
    link = ClinicPatient(seed_key=f"{DEMO_CLINIC_KEY}-link-history", clinic_id=clinic.id, patient_id=patient.id, display_name_ar="مريض تجريبي 6", file_number="DEMO-0006")
    session.add(link)
    session.flush()
    doctor = session.exec(select(Doctor).where(Doctor.seed_key == f"{DEMO_CLINIC_KEY}-doctor-3")).first()
    if doctor is not None:
        session.add(
            Appointment(
                seed_key=f"{DEMO_CLINIC_KEY}-appointment-virtual",
                clinic_id=clinic.id,
                doctor_id=doctor.id,
                clinic_patient_id=link.id,
                scheduled_at=datetime(2026, 11, 25, 10, 0, tzinfo=RIYADH),
                status=AppointmentStatus.scheduled,
                booking_source=BookingSource.vitala,
                visit_reason_ar="متابعة السكري عن بعد",
                appointment_type=AppointmentType.virtual,
            )
        )
    session.commit()
    session.refresh(patient)
    return patient, True


def main() -> None:
    settings = Settings()
    engine = build_engine(settings.database_path)
    init_db(engine, settings.database_path, settings.backup_dir)
    with Session(engine) as session:
        patient, created = seed_synthetic_patient(session)
        outcome = "Created" if created else "Already exists, nothing changed:"
        print(f"{outcome} synthetic patient id={patient.id} in {settings.database_path}")
        clinic, created = seed_demo_clinic(session)
        outcome = "Created" if created else "Already exists, nothing changed:"
        print(f"{outcome} demo clinic id={clinic.id} in {settings.database_path}")
        history_patient, created = seed_history_demo(session, clinic)
        outcome = "Created" if created else "Already exists, nothing changed:"
        print(f"{outcome} synthetic history demo patient id={history_patient.id} in {settings.database_path}")
    engine.dispose()


if __name__ == "__main__":
    main()
