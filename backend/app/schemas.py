"""API request and response shapes.

In the update schemas, a field left out of the request keeps its stored value
and a field sent as null is cleared. The routers tell the two apart with
model_dump(exclude_unset=True). Fields typed without "| None" cannot be null:
send "unknown" instead. Their default=None only marks them as optional.
"""

import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.models import ConditionStatus, DiabetesType, RecordSource, Sex, SmokingStatus, YesNoUnknown

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _require_iso_date_text(value: Any) -> Any:
    # Without this, pydantic also reads numbers as timestamps and accepts times.
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise ValueError("Date must be text in YYYY-MM-DD format")
    return value


IsoDate = Annotated[date, BeforeValidator(_require_iso_date_text)]
DoseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TestName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ResultText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
UnitText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
NotesText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
# Strict numbers: "170" or true must fail rather than be read as a measurement.
HeightCm = Annotated[float, Field(ge=50, le=250, strict=True)]
WeightKg = Annotated[float, Field(ge=2, le=350, strict=True)]
ActivityMinutes = Annotated[int, Field(ge=0, le=10080, strict=True)]


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


class ScreeningRecordCreate(RequestSchema):
    test_id: str
    test_name: TestName
    completed_on: IsoDate
    result: ResultText | None = None
    unit: UnitText | None = None
    source: RecordSource
    notes: NotesText | None = None


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
    id: str
    generic_name: str
    name_ar: str
    drug_class: str
    identity_evidence: list[SourceLocator]
    selection_basis_ar: str
    brand_names: list[str]
    monitoring_rule_ids: list[str]


class HealthRead(BaseModel):
    status: str
    database: str


class MissingInput(BaseModel):
    field: str
    # "unknown": VITALA records this field but it is empty for this patient.
    # "not_collected": VITALA does not record this field yet.
    reason: Literal["unknown", "not_collected"]
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


class ScreeningPreview(BaseModel):
    patient_id: int
    evaluated_on: date
    clinically_approved: Literal[False] = False
    auto_schedule_enabled: Literal[False] = False
    notice_ar: str
    actions: list[ScreeningAction]


class SummaryMissingInput(BaseModel):
    field: str
    reason: Literal["unknown", "not_collected"]
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


class ScreeningSummary(BaseModel):
    patient_id: int
    evaluated_on: date
    clinically_approved: Literal[False] = False
    auto_schedule_enabled: Literal[False] = False
    notice_ar: str
    tests: list[ScreeningTestSummary]
    unmapped_records: list[ScreeningRecordRead]
