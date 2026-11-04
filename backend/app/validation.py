"""Consistency checks that depend on several fields or on stored records.

They run on the final values, so a partial update is judged by the record it
would produce. These are data-entry checks only, not clinical criteria.
"""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.models import ConditionStatus, DiabetesType, MedicationUse, ScreeningRecord


def raise_if_invalid(errors: Mapping[str, str]) -> None:
    """Raise a 422 in the same shape FastAPI uses for its own validation errors."""
    if errors:
        detail = [{"loc": ["body", field], "msg": message, "type": "value_error"} for field, message in errors.items()]
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def profile_errors(profile: Mapping[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    today = date.today()
    birth = profile["date_of_birth"]

    if birth and birth > today:
        errors["date_of_birth"] = "Date of birth cannot be in the future"

    for condition in ("diabetes", "hypertension"):
        field = f"{condition}_diagnosis_date"
        diagnosed_on = profile[field]
        if not diagnosed_on:
            continue
        if profile[f"{condition}_status"] != ConditionStatus.diagnosed:
            errors[field] = f"A diagnosis date requires {condition}_status to be 'diagnosed'"
        elif diagnosed_on > today:
            errors[field] = "Diagnosis date cannot be in the future"
        elif birth and diagnosed_on < birth:
            errors[field] = "Diagnosis date cannot be before the date of birth"

    if profile["diabetes_type"] != DiabetesType.unknown and profile["diabetes_status"] != ConditionStatus.diagnosed:
        errors["diabetes_type"] = "A diabetes type requires diabetes_status to be 'diagnosed'"

    return errors


def birth_date_conflict(
    birth: date | None,
    uses: Iterable[MedicationUse],
    records: Iterable[ScreeningRecord],
) -> dict[str, str]:
    """Check a changed date of birth against medication and screening dates already stored."""
    if birth:
        for use in uses:
            dates = (use.start_date, use.last_dose_change_date)
            if any(known and known < birth for known in dates):
                return {"date_of_birth": f"Date of birth is after the recorded dates of {use.medication_id}"}
        for record in records:
            if record.completed_on < birth:
                return {"date_of_birth": f"Date of birth is after the recorded {record.test_id} test on {record.completed_on}"}
    return {}


def screening_record_errors(record: Mapping[str, Any], birth: date | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    completed_on = record["completed_on"]

    if completed_on > date.today():
        errors["completed_on"] = "Date cannot be in the future"
    elif birth and completed_on < birth:
        errors["completed_on"] = "Date cannot be before the patient's date of birth"

    if record["unit"] and not record["result"]:
        errors["unit"] = "A unit requires a result"

    return errors


def medication_date_errors(
    start: date | None,
    last_change: date | None,
    birth: date | None,
) -> dict[str, str]:
    errors: dict[str, str] = {}
    today = date.today()

    for field, value in (("start_date", start), ("last_dose_change_date", last_change)):
        if value and value > today:
            errors[field] = "Date cannot be in the future"
        elif value and birth and value < birth:
            errors[field] = "Date cannot be before the patient's date of birth"

    if start and last_change and last_change < start and "last_dose_change_date" not in errors:
        errors["last_dose_change_date"] = "Last dose change cannot be before the start date"

    return errors
