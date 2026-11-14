"""API request and response shapes.

In the update schemas, a field left out of the request keeps its stored value
and a field sent as null is cleared. The routers tell the two apart with
model_dump(exclude_unset=True). Fields typed without "| None" cannot be null:
send "unknown" instead. Their default=None only marks them as optional.
"""

import re
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

from app.models import (
    AllergenCategory,
    AllergySeverity,
    AppointmentStatus,
    AppointmentType,
    BookingSource,
    ConditionStatus,
    CoverageStatus,
    DiabetesType,
    FamilyConditionCategory,
    FamilyRelationship,
    RecordSource,
    Sex,
    SmokingStatus,
    Verification,
    YesNoUnknown,
)

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _require_iso_date_text(value: Any) -> Any:
    # Without this, pydantic also reads numbers as timestamps and accepts times.
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise ValueError("Date must be text in YYYY-MM-DD format")
    return value


IsoDate = Annotated[date, BeforeValidator(_require_iso_date_text)]

ISO_AWARE_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})")


def _require_aware_iso_text(value: Any) -> Any:
    # A wall-clock time without an offset is ambiguous across clinics, and a
    # number would be read as a Unix timestamp.
    if not isinstance(value, str) or not ISO_AWARE_DATETIME.fullmatch(value):
        raise ValueError("Time must be ISO 8601 text with a time zone offset, such as 2026-11-09T09:00:00+03:00")
    return value


AwareTimestamp = Annotated[AwareDatetime, BeforeValidator(_require_aware_iso_text)]
DoseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TestName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ResultText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
UnitText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
NotesText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
# Strict numbers: "170" or true must fail rather than be read as a measurement.
HeightCm = Annotated[float, Field(ge=50, le=250, strict=True)]
WeightKg = Annotated[float, Field(ge=2, le=350, strict=True)]
ActivityMinutes = Annotated[int, Field(ge=0, le=10080, strict=True)]
ReferenceRange = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
AgeAtDiagnosis = Annotated[int, Field(ge=0, le=120, strict=True)]


class RequestSchema(BaseModel):
    # A misspelled field must fail rather than be silently ignored.
    model_config = ConfigDict(extra="forbid")


class PatientCreate(RequestSchema):
    date_of_birth: IsoDate | None = None
    sex: Sex = Sex.unknown
    diabetes_status: ConditionStatus = ConditionStatus.unknown
    diabetes_type: DiabetesType = DiabetesType.unknown
    diabetes_diagnosis_date: IsoDate | None = None
    hypertension_status: ConditionStatus = ConditionStatus.unknown
    hypertension_diagnosis_date: IsoDate | None = None


class PatientUpdate(RequestSchema):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"hypertension_status": "not_diagnosed"}]},
    )

    date_of_birth: IsoDate | None = None
    sex: Sex = Field(default=None)
    diabetes_status: ConditionStatus = Field(default=None)
    diabetes_type: DiabetesType = Field(default=None)
    diabetes_diagnosis_date: IsoDate | None = None
    hypertension_status: ConditionStatus = Field(default=None)
    hypertension_diagnosis_date: IsoDate | None = None


class PatientRead(BaseModel):
    id: int
    date_of_birth: date | None
    sex: Sex
    diabetes_status: ConditionStatus
    diabetes_type: DiabetesType
    diabetes_diagnosis_date: date | None
    hypertension_status: ConditionStatus
    hypertension_diagnosis_date: date | None


class ClinicRead(BaseModel):
    id: int
    name_ar: str
    city_ar: str | None
    time_zone: str
    is_demo: bool


class DoctorRead(BaseModel):
    id: int
    clinic_id: int
    name_ar: str
    specialty_ar: str | None


class ClinicPatientRead(BaseModel):
    id: int
    clinic_id: int
    display_name_ar: str
    file_number: str | None
    patient: PatientRead


class AppointmentRead(BaseModel):
    id: int
    clinic_id: int
    doctor_id: int
    clinic_patient_id: int
    scheduled_at: datetime
    status: AppointmentStatus
    booking_source: BookingSource
    visit_reason_ar: str | None
    appointment_type: AppointmentType = AppointmentType.in_person
    # Extension point for in-app video visits. Video is not implemented, so a
    # virtual appointment always reads "not_available" (see app/virtual_care.py).
    virtual_session_status: Literal["not_applicable", "not_available"] = "not_applicable"

    @model_validator(mode="after")
    def derive_virtual_status(self) -> "AppointmentRead":
        self.virtual_session_status = "not_available" if self.appointment_type == AppointmentType.virtual else "not_applicable"
        return self


VisitReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class AppointmentCreate(RequestSchema):
    # Status and booking source are set by the server: scheduled, booked by the clinic.
    clinic_patient_id: int = Field(strict=True)
    doctor_id: int = Field(strict=True)
    scheduled_at: AwareTimestamp
    visit_reason_ar: VisitReason | None = None
    appointment_type: AppointmentType = AppointmentType.in_person


class AppointmentUpdate(RequestSchema):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"scheduled_at": "2026-11-20T10:00:00+03:00"}]},
    )

    doctor_id: int = Field(default=None, strict=True)
    scheduled_at: AwareTimestamp = Field(default=None)
    visit_reason_ar: VisitReason | None = None
    appointment_type: AppointmentType = Field(default=None)


class AppointmentStatusChange(RequestSchema):
    status: Literal["completed", "cancelled", "no_show"]


class AppointmentDetail(BaseModel):
    appointment: AppointmentRead
    doctor: DoctorRead
    patient: ClinicPatientRead


class MedicationUseCreate(RequestSchema):
    medication_id: str
    dose_text: DoseText
    start_date: IsoDate | None = None
    last_dose_change_date: IsoDate | None = None


class MedicationUseUpdate(RequestSchema):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"dose_text": "850 mg twice daily"}]},
    )

    dose_text: DoseText = Field(default=None)
    start_date: IsoDate | None = None
    last_dose_change_date: IsoDate | None = None


class MedicationUseRead(BaseModel):
    id: int
    patient_id: int
    medication_id: str
    dose_text: str
    start_date: date | None
    last_dose_change_date: date | None


class RiskProfileCreate(RequestSchema):
    smoking_status: SmokingStatus = SmokingStatus.unknown
    height_cm: HeightCm | None = None
    weight_kg: WeightKg | None = None
    activity_minutes_per_week: ActivityMinutes | None = None
    raised_lipids: YesNoUnknown = YesNoUnknown.unknown
    pregnancy_status: YesNoUnknown = YesNoUnknown.unknown
    family_diabetes: YesNoUnknown = YesNoUnknown.unknown
    family_heart_disease: YesNoUnknown = YesNoUnknown.unknown
    family_breast_cancer: YesNoUnknown = YesNoUnknown.unknown
    family_colorectal_cancer: YesNoUnknown = YesNoUnknown.unknown
    information_source: Verification = Verification.unknown
    known_allergies: YesNoUnknown = YesNoUnknown.unknown
    family_cancer_history: YesNoUnknown = YesNoUnknown.unknown
    family_chronic_or_autoimmune_history: YesNoUnknown = YesNoUnknown.unknown
    known_genetic_findings: YesNoUnknown = YesNoUnknown.unknown


class RiskProfileUpdate(RequestSchema):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"smoking_status": "never", "height_cm": 165}]},
    )

    smoking_status: SmokingStatus = Field(default=None)
    height_cm: HeightCm | None = None
    weight_kg: WeightKg | None = None
    activity_minutes_per_week: ActivityMinutes | None = None
    raised_lipids: YesNoUnknown = Field(default=None)
    pregnancy_status: YesNoUnknown = Field(default=None)
    family_diabetes: YesNoUnknown = Field(default=None)
    family_heart_disease: YesNoUnknown = Field(default=None)
    family_breast_cancer: YesNoUnknown = Field(default=None)
    family_colorectal_cancer: YesNoUnknown = Field(default=None)
    information_source: Verification = Field(default=None)
    known_allergies: YesNoUnknown = Field(default=None)
    family_cancer_history: YesNoUnknown = Field(default=None)
    family_chronic_or_autoimmune_history: YesNoUnknown = Field(default=None)
    known_genetic_findings: YesNoUnknown = Field(default=None)


class RiskProfileRead(BaseModel):
    patient_id: int
    # False when nothing has been saved yet: every value below is then unknown.
    stored: bool
    smoking_status: SmokingStatus
    height_cm: float | None
    weight_kg: float | None
    bmi: float | None
    activity_minutes_per_week: int | None
    raised_lipids: YesNoUnknown
    pregnancy_status: YesNoUnknown
    family_diabetes: YesNoUnknown
    family_heart_disease: YesNoUnknown
    family_breast_cancer: YesNoUnknown
    family_colorectal_cancer: YesNoUnknown
    # Where the values above come from. One source for the whole profile.
    information_source: Verification = Verification.unknown
    # "no" is a confirmed negative; "unknown" means not asked or not answered.
    known_allergies: YesNoUnknown = YesNoUnknown.unknown
    family_cancer_history: YesNoUnknown = YesNoUnknown.unknown
    family_chronic_or_autoimmune_history: YesNoUnknown = YesNoUnknown.unknown
    known_genetic_findings: YesNoUnknown = YesNoUnknown.unknown


class ScreeningRecordCreate(RequestSchema):
    test_id: str
    test_name: TestName
    completed_on: IsoDate
    result: ResultText | None = None
    unit: UnitText | None = None
    source: RecordSource
    notes: NotesText | None = None
    reference_range: ReferenceRange | None = None


class ClinicScreeningRecordCreate(RequestSchema):
    # No source and no patient id: the server sets clinician_entered and takes the
    # patient from the clinic-patient link in the path.
    test_id: str
    test_name: TestName
    completed_on: IsoDate
    result: ResultText | None = None
    unit: UnitText | None = None
    notes: NotesText | None = None
    reference_range: ReferenceRange | None = None


class ScreeningRecordUpdate(RequestSchema):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"notes": "Synthetic correction"}]},
    )

    test_name: TestName = Field(default=None)
    completed_on: IsoDate = Field(default=None)
    result: ResultText | None = None
    unit: UnitText | None = None
    source: RecordSource = Field(default=None)
    notes: NotesText | None = None
    reference_range: ReferenceRange | None = None


class ScreeningRecordRead(BaseModel):
    id: int
    patient_id: int
    test_id: str
    test_name: str
    completed_on: date
    result: str | None
    unit: str | None
    source: RecordSource
    notes: str | None
    # As printed by the laboratory. Null means VITALA was not given one; it never supplies one.
    reference_range: str | None = None


class ScreeningTestRead(BaseModel):
    id: str
    name_ar: str
    rule_ids: list[str]
    possible_overlap_test_ids: list[str]
    mapping_status: Literal["draft_not_clinician_reviewed"] = "draft_not_clinician_reviewed"


class SourceLocator(BaseModel):
    source_id: str
    locator: str


class CatalogueMedication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    generic_name: str
    name_ar: str
    drug_class: str
    identity_evidence: list[SourceLocator]
    selection_basis_ar: str
    brand_names: list[str]
    monitoring_rule_ids: list[str]
    # Archived entries stay readable so recorded uses keep their names, but new
    # uses cannot be added and their rules are not evaluated.
    status: Literal["active", "archived"]
    demo_scope: Literal["metformin", "ace_inhibitor"] | None
    archived_on: date | None
    archive_reason_ar: str | None


class HealthRead(BaseModel):
    status: str
    database: str


class MissingInput(BaseModel):
    field: str
    # "unknown": VITALA records this field but it is empty for this patient.
    # "not_collected": VITALA does not record this field yet.
    # "recorded_pending_review": VITALA has a value, but no approved mapping lets
    # the draft rules use it yet (see risk_inputs.py).
    reason: Literal["unknown", "not_collected", "recorded_pending_review"]
    affects_eligibility: bool


class SourceReference(BaseModel):
    source_id: str
    locator: str
    title: str
    issuer: str
    url: str
    version: str | None
    limitation_ar: str


class ScreeningAction(BaseModel):
    rule_id: str
    track: str
    action_id: str
    action_name_ar: str
    eligibility_ar: str
    status: Literal["candidate", "needs_information", "not_applicable", "not_triggered"]
    reasons: list[str]
    missing_inputs: list[MissingInput]
    matched_medication_ids: list[str]
    schedule_text_ar: str
    notes_ar: str
    review_flags: list[str]
    conflict_ids: list[str]
    knowledge_ids: list[str]
    sources: list[SourceReference]
    review_status: str
    auto_schedule_enabled: Literal[False]


class RiskFactRead(BaseModel):
    field: str
    # "unknown" is never a negative finding.
    state: Literal["present", "absent", "unknown", "value"]
    value: str | float | int | None
    source: Verification
    # Draft rules that name this field.
    rule_ids: list[str]
    # True only when an approved mapping lets a rule use this value. None are approved yet.
    actionable: bool
    actionable_rule_ids: list[str]
    detail: dict[str, Any] = {}


class OutOfScopeMedication(BaseModel):
    # A recorded use of an archived catalogue entry. Kept, but no rule is evaluated for it.
    use_id: int | None
    medication_id: str


class ScreeningPreview(BaseModel):
    patient_id: int
    evaluated_on: date
    clinically_approved: Literal[False] = False
    auto_schedule_enabled: Literal[False] = False
    notice_ar: str
    actions: list[ScreeningAction]
    risk_factors: list[RiskFactRead] = []
    out_of_scope_medications: list[OutOfScopeMedication] = []


class SummaryMissingInput(BaseModel):
    field: str
    reason: Literal["unknown", "not_collected", "recorded_pending_review"]
    affects_eligibility: bool
    rule_ids: list[str]


class HistoryMappingRead(BaseModel):
    id: str
    version: int
    test_id: str
    field: str
    kind: Literal["completion_date", "test_on_record"]
    status: Literal["pending_review", "approved"]
    reviewer: str | None
    reviewed_on: date | None
    rule_ids: list[str]
    changes_eligibility: bool


class AmbiguousHistoryFieldRead(BaseModel):
    test_id: str
    field: str
    rule_ids: list[str]
    reason: str


class HistoryMappingCatalogue(BaseModel):
    mappings: list[HistoryMappingRead]
    ambiguous: list[AmbiguousHistoryFieldRead]
    clinical_interpretation_fields: list[str]


class HistoryInput(BaseModel):
    mapping_id: str
    version: int
    field: str
    kind: Literal["completion_date", "test_on_record"]
    status: Literal["pending_review", "approved"]
    applied: bool
    changes_eligibility: bool
    rule_ids: list[str]
    record_count: int
    latest_completed_on: date | None
    latest_record_id: int | None


class ScreeningTestSummary(BaseModel):
    test_id: str
    name_ar: str
    mapping_status: Literal["draft_not_clinician_reviewed"] = "draft_not_clinician_reviewed"
    recorded_tests: list[ScreeningRecordRead]
    history_inputs: list[HistoryInput]
    ambiguous_history_fields: list[AmbiguousHistoryFieldRead]
    candidate_rule_ids: list[str]
    needs_information_rule_ids: list[str]
    not_applicable_rule_ids: list[str]
    not_triggered_rule_ids: list[str]
    missing_inputs: list[SummaryMissingInput]
    review_reasons: list[str]
    conflict_ids: list[str]
    possible_overlap_test_ids: list[str]
    rules: list[ScreeningAction]
    # Rules of this test archived with the medication scope change. Not evaluated.
    archived_rule_ids: list[str] = []


class ScreeningSummary(BaseModel):
    patient_id: int
    evaluated_on: date
    clinically_approved: Literal[False] = False
    auto_schedule_enabled: Literal[False] = False
    notice_ar: str
    tests: list[ScreeningTestSummary]
    unmapped_records: list[ScreeningRecordRead]
    risk_factors: list[RiskFactRead] = []
    out_of_scope_medications: list[OutOfScopeMedication] = []


class SummaryMedication(BaseModel):
    id: int
    medication_id: str
    # None when the id is not in the catalogue. The record itself stores no source.
    name_ar: str | None
    generic_name: str | None
    drug_class: str | None
    dose_text: str
    start_date: date | None
    last_dose_change_date: date | None
    # "archived": recorded before the medication scope change; kept unchanged, no rule evaluated.
    catalogue_status: Literal["active", "archived"] | None = None


# ---------------------------------------------------------------- medical history


class AllergyCreate(RequestSchema):
    allergen: ShortText
    category: AllergenCategory = AllergenCategory.unknown
    reaction: LongText | None = None
    severity: AllergySeverity = AllergySeverity.unknown
    verification: Verification = Verification.unknown
    notes: NotesText | None = None


class AllergyUpdate(RequestSchema):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"severity": "severe"}]})

    allergen: ShortText = Field(default=None)
    category: AllergenCategory = Field(default=None)
    reaction: LongText | None = None
    severity: AllergySeverity = Field(default=None)
    verification: Verification = Field(default=None)
    notes: NotesText | None = None


class AllergyRead(BaseModel):
    id: int
    patient_id: int
    allergen: str
    category: AllergenCategory
    reaction: str | None
    severity: AllergySeverity
    verification: Verification
    notes: str | None


class FamilyConditionCreate(RequestSchema):
    category: FamilyConditionCategory
    # A code from GET /medical-history/vocabulary for the category, or "other" with condition_other.
    condition: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    condition_other: ShortText | None = None
    age_at_diagnosis: AgeAtDiagnosis | None = None
    verification: Verification = Verification.unknown


class FamilyConditionUpdate(RequestSchema):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"age_at_diagnosis": 52}]})

    age_at_diagnosis: AgeAtDiagnosis | None = None
    verification: Verification = Field(default=None)


class FamilyConditionRead(BaseModel):
    id: int
    relative_id: int
    category: FamilyConditionCategory
    condition: str
    condition_other: str | None
    age_at_diagnosis: int | None
    verification: Verification


class FamilyRelativeCreate(RequestSchema):
    relationship: FamilyRelationship
    label: ShortText | None = None
    # Optional: add the relative's conditions in the same request.
    conditions: list[FamilyConditionCreate] = Field(default=[], max_length=20)


class FamilyRelativeUpdate(RequestSchema):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"label": "older sister"}]})

    relationship: FamilyRelationship = Field(default=None)
    label: ShortText | None = None


class FamilyRelativeRead(BaseModel):
    id: int
    patient_id: int
    relationship: FamilyRelationship
    # By definition of the relationship only; half-siblings count as first degree here.
    degree: Literal["first", "second", "other", "unknown"]
    label: str | None
    conditions: list[FamilyConditionRead]


class GeneticFindingCreate(RequestSchema):
    name: ShortText
    gene: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    verification: Verification = Verification.unknown
    test_source: ShortText | None = None
    test_date: IsoDate | None = None
    notes: NotesText | None = None


class GeneticFindingUpdate(RequestSchema):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"verification": "clinically_confirmed"}]})

    name: ShortText = Field(default=None)
    gene: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    verification: Verification = Field(default=None)
    test_source: ShortText | None = None
    test_date: IsoDate | None = None
    notes: NotesText | None = None


class GeneticFindingRead(BaseModel):
    id: int
    patient_id: int
    name: str
    gene: str | None
    verification: Verification
    test_source: str | None
    test_date: date | None
    notes: str | None


class FamilyHistoryCounts(BaseModel):
    # Distinct relatives, so a relative with two conditions counts once.
    relatives_with_cancer: int
    first_degree_relatives_with_cancer: int
    relatives_with_chronic_or_autoimmune: int


class ConsistencyNote(BaseModel):
    field: str
    message: str


class MedicalHistoryRead(BaseModel):
    """Everything VITALA records about history and risk. Read-only and never interpreted."""

    patient_id: int
    risk_profile: RiskProfileRead
    allergies: list[AllergyRead]
    family_relatives: list[FamilyRelativeRead]
    family_counts: FamilyHistoryCounts
    genetic_findings: list[GeneticFindingRead]
    # Each risk factor with its state and source, and whether any approved rule uses it.
    risk_factors: list[RiskFactRead]
    # Summary flags that a structured record contradicts or refines. Nothing is changed automatically.
    consistency_notes: list[ConsistencyNote]
    screening_uses_risk_factors: Literal[False] = False
    notice: str = (
        "Recorded for the clinician and the patient. No risk factor, allergy, family or genetic record "
        "changes a screening status until a clinician approves the mapping."
    )


class VocabularyRead(BaseModel):
    relationships: list[str]
    conditions: dict[str, list[str]]
    allergen_categories: list[str]
    allergy_severities: list[str]
    verification: list[str]


# ---------------------------------------------------------------- insurance

NationalId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[12]\d{9}$")]
MemberNumber = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9-]{3,40}$")]


class InsuranceUpdate(RequestSchema):
    """Full replacement of the patient's insurance details (PUT). Omitted fields are cleared."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "coverage_status": "insured",
                    "national_id": "1000000008",
                    "insurer_name": "Synthetic Insurer",
                    "member_number": "SYN-123456",
                    "insurance_class": "B",
                }
            ]
        },
    )

    coverage_status: CoverageStatus
    # 10 digits starting with 1 (citizen) or 2 (resident). Format check only.
    national_id: NationalId | None = None
    insurer_name: ShortText | None = None
    member_number: MemberNumber | None = None
    insurance_class: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)] | None = None


class InsuranceRead(BaseModel):
    patient_id: int
    stored: bool
    coverage_status: CoverageStatus
    insurer_name: str | None
    insurance_class: str | None
    # Masked: only the last four characters are ever returned.
    national_id_masked: str | None
    member_number_masked: str | None
    updated_at: datetime | None
    eligibility_verified: Literal[False] = False
    insurer_integration_available: Literal[False] = False
    online_payment_available: Literal[False] = False


class InsuranceSummary(BaseModel):
    # What the clinician summary shows: no identifiers, not even masked.
    coverage_status: CoverageStatus
    insurer_name: str | None
    insurance_class: str | None
    eligibility_verified: Literal[False] = False


# ---------------------------------------------------------------- chatbot

ChatLanguage = Literal["ar", "en"]


class ChatRequest(RequestSchema):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    # Optional. Only synthetic demo patients (created by app.seed) may be used as
    # context; any other patient returns 403 until authentication exists.
    patient_id: int | None = Field(default=None, strict=True)


class ChatCitation(BaseModel):
    evidence_id: str
    source_id: str
    collection: str
    title: str
    citation: str
    url: str = ""
    pdf_page: int | None = None


class ChatPatientContextInfo(BaseModel):
    used: bool
    synthetic: bool
    patient_id: int | None = None
    fields_sent: list[str] = []


class ChatReply(BaseModel):
    request_id: str
    # The RAG status: answered, insufficient_evidence, emergency_escalation,
    # declined_personal_advice, declined_out_of_scope, grounding_fallback, patient_data_unavailable, error.
    status: str
    language: str
    # Grounded answer with [E#]/[P#] citation markers.
    answer: str
    # Patient-facing text without markers. Show this in the app.
    display_text: str
    notices: list[str]
    citations: list[ChatCitation]
    safety_flags: list[str]
    route: str
    disclaimer: str
    llm_provider: str
    patient_context: ChatPatientContextInfo
    is_medical_advice: Literal[False] = False


class ChatStatus(BaseModel):
    available: bool
    reason: str | None = None
    llm_provider: str | None = None
    pipeline_version: str | None = None
    patient_context_policy: Literal["synthetic_demo_patients_only"] = "synthetic_demo_patients_only"


class ResultAnalysisRequest(RequestSchema):
    language: ChatLanguage = "ar"


class AnalyzedResult(BaseModel):
    record_id: int
    test_id: str
    test_name: str
    result: str | None
    unit: str | None
    completed_on: date
    reference_range: str | None
    source: RecordSource
    # Fields the record does not have. Nothing is filled in.
    missing_fields: list[str]


class ResultAnalysisRead(BaseModel):
    result: AnalyzedResult
    explanation: ChatReply
    limitations: list[str]
    interpreted_by_vitala: Literal[False] = False


# ---------------------------------------------------------------- clinician summary


class PreAppointmentSummary(BaseModel):
    # Read-only and built from existing records. Nothing here is clinically validated.
    clinic: ClinicRead
    visit: AppointmentDetail
    risk_profile: RiskProfileRead
    medications: list[SummaryMedication]
    screening: ScreeningSummary
    # Allergies, structured family history, genetic findings, risk-factor states.
    medical_history: MedicalHistoryRead | None = None
    insurance: InsuranceSummary | None = None
    smartwatch_data_available: Literal[False] = False
    clinically_validated: Literal[False] = False
