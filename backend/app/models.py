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


class AppointmentType(StrEnum):
    # Rows created before this field existed are in_person: VITALA had no virtual visits then.
    in_person = "in_person"
    virtual = "virtual"


class Verification(StrEnum):
    # Where a fact comes from. Patient-reported is never presented as confirmed.
    patient_reported = "patient_reported"
    clinically_confirmed = "clinically_confirmed"
    unknown = "unknown"


class AllergenCategory(StrEnum):
    drug = "drug"
    food = "food"
    environmental = "environmental"
    other = "other"
    unknown = "unknown"


class AllergySeverity(StrEnum):
    mild = "mild"
    moderate = "moderate"
    severe = "severe"
    life_threatening = "life_threatening"
    unknown = "unknown"


class FamilyRelationship(StrEnum):
    mother = "mother"
    father = "father"
    sister = "sister"
    brother = "brother"
    half_sister = "half_sister"
    half_brother = "half_brother"
    daughter = "daughter"
    son = "son"
    maternal_grandmother = "maternal_grandmother"
    maternal_grandfather = "maternal_grandfather"
    paternal_grandmother = "paternal_grandmother"
    paternal_grandfather = "paternal_grandfather"
    maternal_aunt = "maternal_aunt"
    maternal_uncle = "maternal_uncle"
    paternal_aunt = "paternal_aunt"
    paternal_uncle = "paternal_uncle"
    cousin = "cousin"
    other = "other"
    unknown = "unknown"


class FamilyConditionCategory(StrEnum):
    cancer = "cancer"
    chronic = "chronic"
    autoimmune = "autoimmune"


class CoverageStatus(StrEnum):
    insured = "insured"
    uninsured = "uninsured"
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
    # The screening engine sees it only as a RiskContext (risk_inputs.py), and no
    # value changes a status until a mapping is approved. Unknown never means "no".
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
    # Added by migration 2026-11-14-03. "no" is a confirmed negative and cannot
    # coexist with structured records that say otherwise; "unknown" is not "no".
    information_source: Verification = Verification.unknown
    known_allergies: YesNoUnknown = YesNoUnknown.unknown
    family_cancer_history: YesNoUnknown = YesNoUnknown.unknown
    family_chronic_or_autoimmune_history: YesNoUnknown = YesNoUnknown.unknown
    known_genetic_findings: YesNoUnknown = YesNoUnknown.unknown


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
    # Added by migration 2026-11-14-01.
    appointment_type: AppointmentType = AppointmentType.in_person
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
    # The laboratory's own reference range, as printed. Added by migration 2026-11-14-02.
    # VITALA never supplies or guesses a range.
    reference_range: str | None = None


class Allergy(SQLModel, table=True):
    # Medical history only. Allergies never trigger screening recommendations.
    __table_args__ = (UniqueConstraint("patient_id", "allergen_key"),)

    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    allergen: str
    # Lower-cased, whitespace-collapsed allergen, so "Penicillin" is not stored twice.
    allergen_key: str
    category: AllergenCategory = AllergenCategory.unknown
    reaction: str | None = None
    severity: AllergySeverity = AllergySeverity.unknown
    verification: Verification = Verification.unknown
    notes: str | None = None


class FamilyRelative(SQLModel, table=True):
    # One row per affected relative, so a relative with two conditions is counted once.
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    relationship: FamilyRelationship
    # Optional label that tells two relatives with the same relationship apart, e.g. "older sister".
    label: str | None = None


class FamilyCondition(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("relative_id", "category", "condition", "condition_other"),)

    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    relative_id: int = Field(foreign_key="familyrelative.id", index=True)
    category: FamilyConditionCategory
    # A code from app/medical_history.py for the category, or "other" with condition_other.
    condition: str
    condition_other: str | None = None
    age_at_diagnosis: int | None = None
    verification: Verification = Verification.unknown


class GeneticFinding(SQLModel, table=True):
    # Recorded as reported. VITALA infers no risk and no screening from it.
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    name: str
    gene: str | None = None
    verification: Verification = Verification.unknown
    test_source: str | None = None
    test_date: date | None = None
    notes: str | None = None


class PatientInsurance(SQLModel, table=True):
    # Highly sensitive. Identifiers are stored encrypted, with only the last four
    # characters in clear for masking, and a keyed hash to detect duplicates.
    # The national ID lives only in this table.
    patient_id: int = Field(foreign_key="patient.id", primary_key=True)
    coverage_status: CoverageStatus = CoverageStatus.unknown
    insurer_name: str | None = None
    insurance_class: str | None = None
    national_id_ciphertext: str | None = None
    national_id_last4: str | None = None
    national_id_hash: str | None = Field(default=None, unique=True)
    member_number_ciphertext: str | None = None
    member_number_last4: str | None = None
    updated_at: datetime | None = None
