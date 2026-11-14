"""Consistency checks that depend on several fields or on stored records.

They run on the final values, so a partial update is judged by the record it
would produce. These are data-entry checks only, not clinical criteria.
"""

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.models import AppointmentStatus, ConditionStatus, DiabetesType, MedicationUse, ScreeningRecord, Sex, YesNoUnknown

# Demo policy: appointments have no stored duration, so one doctor's scheduled
# appointments must start at least this far apart.
APPOINTMENT_SLOT = timedelta(minutes=30)
BOOKING_HORIZON = timedelta(days=365)

# The only allowed changes. Completed, cancelled, and no-show are final.
STATUS_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.scheduled: {AppointmentStatus.completed, AppointmentStatus.cancelled, AppointmentStatus.no_show},
}
NEEDS_TIME_PASSED = {AppointmentStatus.completed, AppointmentStatus.no_show}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def pregnancy_conflict(sex: Sex, pregnancy_status: YesNoUnknown, field: str) -> dict[str, str]:
    """A data-entry check only. It decides nothing about screening."""
    if sex == Sex.male and pregnancy_status == YesNoUnknown.yes:
        if field == "sex":
            return {"sex": "Sex cannot be male while pregnancy is recorded as yes"}
        return {field: "Pregnancy cannot be yes for a patient recorded as male"}
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


def appointment_time_errors(scheduled_at: datetime, now: datetime) -> dict[str, str]:
    if scheduled_at <= now:
        return {"scheduled_at": "Appointment time must be in the future"}
    if scheduled_at > now + BOOKING_HORIZON:
        return {"scheduled_at": "Appointment time cannot be more than 365 days ahead"}
    return {}


def doctor_conflict_errors(scheduled_at: datetime, doctor_times: Iterable[datetime]) -> dict[str, str]:
    """doctor_times: the start times of the doctor's other scheduled appointments."""
    if any(abs(scheduled_at - other) < APPOINTMENT_SLOT for other in doctor_times):
        return {"scheduled_at": "The doctor already has an appointment within 30 minutes of this time"}
    return {}


def status_change_errors(
    current: AppointmentStatus,
    new: AppointmentStatus,
    scheduled_at: datetime,
    now: datetime,
) -> dict[str, str]:
    if new not in STATUS_TRANSITIONS.get(current, set()):
        return {"status": f"Cannot change a {current} appointment to {new}"}
    if new in NEEDS_TIME_PASSED and scheduled_at > now:
        return {"status": f"An appointment cannot be marked {new} before its time"}
    return {}
