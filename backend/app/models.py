"""Database tables. API request and response shapes live in schemas.py."""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Sex(StrEnum):
    male = "male"
    female = "female"
    unknown = "unknown"


class ConditionStatus(StrEnum):
    diagnosed = "diagnosed"
    not_diagnosed = "not_diagnosed"
    unknown = "unknown"


class DiabetesType(StrEnum):
    type_1 = "type_1"
    type_2 = "type_2"
    other = "other"
    unknown = "unknown"


class SmokingStatus(StrEnum):
    current = "current"
    former = "former"
    never = "never"
    unknown = "unknown"


class YesNoUnknown(StrEnum):
    yes = "yes"
    no = "no"
    unknown = "unknown"


class AppointmentStatus(StrEnum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class BookingSource(StrEnum):
    vitala = "vitala"
    clinic = "clinic"
    unknown = "unknown"


class RecordSource(StrEnum):
    patient_reported = "patient_reported"
    lab_report = "lab_report"
    clinician_entered = "clinician_entered"
    device = "device"


class Patient(SQLModel, table=True):
    # Missing information stays "unknown" (or NULL for dates). It never means
    # that a condition is absent; only "not_diagnosed" says that.
    id: int | None = Field(default=None, primary_key=True)
    date_of_birth: date | None = None
    sex: Sex = Sex.unknown
    diabetes_status: ConditionStatus = ConditionStatus.unknown
    diabetes_type: DiabetesType = DiabetesType.unknown
    diabetes_diagnosis_date: date | None = None
    hypertension_status: ConditionStatus = ConditionStatus.unknown
    hypertension_diagnosis_date: date | None = None
    # Lets the seed command recognise its own record. Not exposed by the API.
    seed_key: str | None = Field(default=None, unique=True)


class MedicationUse(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("patient_id", "medication_id"),)

    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    # An id from data/medications.json, which is a file rather than a table,
    # so the API checks it against the catalogue instead of a foreign key.
    medication_id: str
    dose_text: str
    start_date: date | None = None
    last_dose_change_date: date | None = None


class PatientRiskProfile(SQLModel, table=True):
    # A separate table, so existing databases gain it without altering Patient.
    # The screening engine does not read it. Unknown never means "no".
    patient_id: int = Field(foreign_key="patient.id", primary_key=True)
    smoking_status: SmokingStatus = SmokingStatus.unknown
    height_cm: float | None = None
    weight_kg: float | None = None
    activity_minutes_per_week: int | None = None
    raised_lipids: YesNoUnknown = YesNoUnknown.unknown
    pregnancy_status: YesNoUnknown = YesNoUnknown.unknown
    family_diabetes: YesNoUnknown = YesNoUnknown.unknown
    family_heart_disease: YesNoUnknown = YesNoUnknown.unknown
    family_breast_cancer: YesNoUnknown = YesNoUnknown.unknown
    family_colorectal_cancer: YesNoUnknown = YesNoUnknown.unknown


class Clinic(SQLModel, table=True):
    # Every clinic-side row carries its clinic, so more clinics can be added later.
    id: int | None = Field(default=None, primary_key=True)
    name_ar: str
    city_ar: str | None = None
    # IANA name used to show appointment times; they are stored in UTC.
    time_zone: str = "Asia/Riyadh"
    is_demo: bool = False
    seed_key: str | None = Field(default=None, unique=True)


class Doctor(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    clinic_id: int = Field(foreign_key="clinic.id", index=True)
    name_ar: str
    specialty_ar: str | None = None
    seed_key: str | None = Field(default=None, unique=True)


class ClinicPatient(SQLModel, table=True):
    # A clinic sees a patient only through this link. Unlinked patients stay private.
    __table_args__ = (UniqueConstraint("clinic_id", "patient_id"),)

    id: int | None = Field(default=None, primary_key=True)
    clinic_id: int = Field(foreign_key="clinic.id", index=True)
    patient_id: int = Field(foreign_key="patient.id")
    display_name_ar: str
    file_number: str | None = None
    seed_key: str | None = Field(default=None, unique=True)


class Appointment(SQLModel, table=True):
    # Points at the clinic-patient link, so a patient's appointment always belongs
    # to a clinic that patient is registered with. scheduled_at is timezone-aware.
    id: int | None = Field(default=None, primary_key=True)
    clinic_id: int = Field(foreign_key="clinic.id", index=True)
    doctor_id: int = Field(foreign_key="doctor.id")
    clinic_patient_id: int = Field(foreign_key="clinicpatient.id")
    scheduled_at: datetime
    status: AppointmentStatus = AppointmentStatus.scheduled
    booking_source: BookingSource = BookingSource.unknown
    visit_reason_ar: str | None = None
    seed_key: str | None = Field(default=None, unique=True)


class ScreeningRecord(SQLModel, table=True):
    # One completed test. A patient may have many records for the same test.
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    # An id from app/screening_tests.py, checked by the API like medication_id.
    test_id: str
    test_name: str
    completed_on: date
    # Stored exactly as reported. VITALA never interprets results.
    result: str | None = None
    unit: str | None = None
    source: RecordSource
    notes: str | None = None
