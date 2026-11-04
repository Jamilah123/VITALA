from datetime import date

from fastapi import APIRouter, Request
from sqlmodel import select

from app.database import SessionDep
from app.models import MedicationUse
from app.routers.profiles import get_patient_or_404
from app.routers.screening_records import list_records
from app.schemas import ScreeningPreview, ScreeningSummary
from app.screening import preview_screening, summarize_screening

router = APIRouter()


@router.get(
    "/patients/{patient_id}/screening-preview",
    response_model=ScreeningPreview,
    tags=["Screening preview"],
    description="Draft rules evaluated against recorded data. Not clinically approved, not a recommendation, schedules nothing.",
)
def screening_preview(patient_id: int, request: Request, session: SessionDep) -> ScreeningPreview:
    patient = get_patient_or_404(session, patient_id)
    uses = session.exec(select(MedicationUse).where(MedicationUse.patient_id == patient_id)).all()
    records = list_records(session, patient_id)
    return preview_screening(request.app.state.rule_set, patient, uses, date.today(), records)


@router.get(
    "/patients/{patient_id}/screening-summary",
    response_model=ScreeningSummary,
    tags=["Screening preview"],
    description=(
        "Draft rules grouped by explicitly mapped test, with the patient's recorded tests. "
        "Not clinically approved, not a recommendation, calculates no due dates."
    ),
)
def screening_summary(patient_id: int, request: Request, session: SessionDep) -> ScreeningSummary:
    patient = get_patient_or_404(session, patient_id)
    uses = session.exec(select(MedicationUse).where(MedicationUse.patient_id == patient_id)).all()
    records = list_records(session, patient_id)
    return summarize_screening(request.app.state.rule_set, patient, uses, records, date.today())
