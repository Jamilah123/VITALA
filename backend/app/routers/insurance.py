"""Insurance and payment information. Demo only: no authentication, synthetic data.

Nothing here verifies eligibility, contacts an insurer, or processes payments.
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.crypto import EncryptionUnavailable, last4, mask
from app.database import SessionDep
from app.models import CoverageStatus, PatientInsurance
from app.routers.profiles import get_patient_or_404
from app.schemas import InsuranceRead, InsuranceSummary, InsuranceUpdate
from app.validation import raise_if_invalid, utc_now

router = APIRouter(prefix="/patients/{patient_id}/insurance", tags=["Insurance"])

DETAIL_FIELDS = ("national_id", "insurer_name", "member_number", "insurance_class")


def insurance_read(patient_id: int, record: PatientInsurance | None) -> InsuranceRead:
    stored = record is not None
    record = record or PatientInsurance(patient_id=patient_id)
    return InsuranceRead(
        patient_id=patient_id,
        stored=stored,
        coverage_status=record.coverage_status,
        insurer_name=record.insurer_name,
        insurance_class=record.insurance_class,
        national_id_masked=mask(record.national_id_last4, 10),
        member_number_masked=mask(record.member_number_last4, 8),
        updated_at=record.updated_at,
    )


def insurance_summary(session: Session, patient_id: int) -> InsuranceSummary:
    record = session.get(PatientInsurance, patient_id) or PatientInsurance(patient_id=patient_id)
    return InsuranceSummary(
        coverage_status=record.coverage_status,
        insurer_name=record.insurer_name,
        insurance_class=record.insurance_class,
    )


@router.get("", response_model=InsuranceRead, description="Masked: identifiers are never returned in full.")
def read_insurance(patient_id: int, session: SessionDep) -> InsuranceRead:
    get_patient_or_404(session, patient_id)
    return insurance_read(patient_id, session.get(PatientInsurance, patient_id))


@router.put(
    "",
    response_model=InsuranceRead,
    description=(
        "Replaces the patient's insurance details. Fields left out are cleared. Detail fields are allowed only when "
        "coverage_status is 'insured'. Saving a national ID or member number needs VITALA_FIELD_ENCRYPTION_KEY."
    ),
)
def replace_insurance(patient_id: int, body: InsuranceUpdate, request: Request, session: SessionDep) -> InsuranceRead:
    get_patient_or_404(session, patient_id)
    values = body.model_dump()
    if body.coverage_status != CoverageStatus.insured:
        raise_if_invalid({field: "Only allowed when coverage_status is 'insured'" for field in DETAIL_FIELDS if values[field] is not None})

    cipher = request.app.state.field_cipher
    record = session.get(PatientInsurance, patient_id) or PatientInsurance(patient_id=patient_id)
    try:
        for field, prefix in (("national_id", "national_id"), ("member_number", "member_number")):
            value = values[field]
            setattr(record, f"{prefix}_ciphertext", cipher.encrypt(value) if value else None)
            setattr(record, f"{prefix}_last4", last4(value) if value else None)
        record.national_id_hash = cipher.identifier_hash(body.national_id) if body.national_id else None
    except EncryptionUnavailable:
        session.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "encryption_not_configured", "message": "National ID and member number cannot be stored until VITALA_FIELD_ENCRYPTION_KEY is set."},
        )
    record.coverage_status = body.coverage_status
    record.insurer_name = body.insurer_name
    record.insurance_class = body.insurance_class
    record.updated_at = utc_now()
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # Does not say which patient holds it.
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "national_id_in_use", "message": "This national ID is already recorded for another patient."})
    session.refresh(record)
    return insurance_read(patient_id, record)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_insurance(patient_id: int, session: SessionDep) -> None:
    get_patient_or_404(session, patient_id)
    record = session.get(PatientInsurance, patient_id)
    if record is not None:
        session.delete(record)
        session.commit()
