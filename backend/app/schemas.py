"""API request and response shapes.

In the update schemas, a field left out of the request keeps its stored value
and a field sent as null is cleared. The routers tell the two apart with
model_dump(exclude_unset=True). Fields typed without "| None" cannot be null:
send "unknown" instead. Their default=None only marks them as optional.
"""

import re
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.models import ConditionStatus, DiabetesType, Sex

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _require_iso_date_text(value: Any) -> Any:
    # Without this, pydantic also reads numbers as timestamps and accepts times.
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        raise ValueError("Date must be text in YYYY-MM-DD format")
    return value


IsoDate = Annotated[date, BeforeValidator(_require_iso_date_text)]
DoseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


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
