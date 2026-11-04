"""Database tables. API request and response shapes live in schemas.py."""

from datetime import date
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
