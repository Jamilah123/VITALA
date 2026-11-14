from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import SessionDep
from app.history_mappings import (
    AMBIGUOUS_HISTORY_FIELDS,
    CLINICAL_INTERPRETATIONS,
    HISTORY_MAPPINGS,
    changes_eligibility,
    mapped_rule_ids,
)
from app.models import Patient, ScreeningRecord
from app.routers.profiles import get_patient_or_404
from app.schemas import (
    AmbiguousHistoryFieldRead,
    HistoryMappingCatalogue,
    HistoryMappingRead,
    ScreeningRecordCreate,
    ScreeningRecordRead,
    ScreeningRecordUpdate,
    ScreeningTestRead,
)
from app.screening_tests import SCREENING_TESTS, possible_overlaps
from app.validation import raise_if_invalid, screening_record_errors

router = APIRouter()


def get_record_or_404(session: Session, patient_id: int, record_id: int) -> ScreeningRecord:
    record = session.get(ScreeningRecord, record_id)
    if record is None or record.patient_id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Screening record {record_id} not found for patient {patient_id}")
    return record


def list_records(session: Session, patient_id: int) -> list[ScreeningRecord]:
    query = (
        select(ScreeningRecord)
        .where(ScreeningRecord.patient_id == patient_id)
        .order_by(ScreeningRecord.completed_on.desc(), ScreeningRecord.id.desc())
    )
    return list(session.exec(query).all())


def create_record(session: Session, patient: Patient, fields: dict) -> ScreeningRecord:
    """The one place a screening record is validated and created, for patient and clinic alike."""
    if fields["test_id"] not in SCREENING_TESTS:
        raise_if_invalid({"test_id": f"'{fields['test_id']}' is not a known screening test"})
    raise_if_invalid(screening_record_errors(fields, patient.date_of_birth))

    record = ScreeningRecord(patient_id=patient.id, **fields)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.get("/screening-tests", response_model=list[ScreeningTestRead], tags=["Screening history"])
def list_screening_tests() -> list[ScreeningTestRead]:
    return [
        ScreeningTestRead(id=test_id, name_ar=test.name_ar, rule_ids=list(test.rule_ids), possible_overlap_test_ids=possible_overlaps(test_id))
        for test_id, test in SCREENING_TESTS.items()
    ]


@router.get("/screening-history-mappings", response_model=HistoryMappingCatalogue, tags=["Screening history"])
def list_history_mappings(request: Request) -> HistoryMappingCatalogue:
    rules = {rule.id: rule for rule in request.app.state.rule_set.rules}
    return HistoryMappingCatalogue(
        mappings=[
            HistoryMappingRead(
                id=mapping.id,
                version=mapping.version,
                test_id=mapping.test_id,
                field=mapping.field,
                kind=mapping.kind,
                status=mapping.status,
                reviewer=mapping.reviewer,
                reviewed_on=mapping.reviewed_on,
                rule_ids=mapped_rule_ids(mapping, rules),
                changes_eligibility=changes_eligibility(mapping, rules),
            )
            for mapping in HISTORY_MAPPINGS
        ],
        ambiguous=[
            AmbiguousHistoryFieldRead(test_id=item.test_id, field=item.field, rule_ids=list(item.rule_ids), reason=item.reason)
            for item in AMBIGUOUS_HISTORY_FIELDS
        ],
        clinical_interpretation_fields=sorted(CLINICAL_INTERPRETATIONS),
    )


@router.post(
    "/patients/{patient_id}/screening-records",
    response_model=ScreeningRecordRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Screening history"],
)
def add_screening_record(patient_id: int, body: ScreeningRecordCreate, session: SessionDep) -> ScreeningRecord:
    return create_record(session, get_patient_or_404(session, patient_id), body.model_dump())


@router.get("/patients/{patient_id}/screening-records", response_model=list[ScreeningRecordRead], tags=["Screening history"])
def list_screening_records(patient_id: int, session: SessionDep) -> list[ScreeningRecord]:
    get_patient_or_404(session, patient_id)
    return list_records(session, patient_id)


@router.patch(
    "/patients/{patient_id}/screening-records/{record_id}",
    response_model=ScreeningRecordRead,
    tags=["Screening history"],
)
def update_screening_record(patient_id: int, record_id: int, body: ScreeningRecordUpdate, session: SessionDep) -> ScreeningRecord:
    patient = get_patient_or_404(session, patient_id)
    record = get_record_or_404(session, patient_id, record_id)
    changes = body.model_dump(exclude_unset=True)
    raise_if_invalid(screening_record_errors(record.model_dump() | changes, patient.date_of_birth))

    record.sqlmodel_update(changes)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.delete(
    "/patients/{patient_id}/screening-records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Screening history"],
)
def remove_screening_record(patient_id: int, record_id: int, session: SessionDep) -> None:
    get_patient_or_404(session, patient_id)
    session.delete(get_record_or_404(session, patient_id, record_id))
    session.commit()
