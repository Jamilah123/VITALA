from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import SessionDep
from app.models import MedicationUse
from app.routers.profiles import get_patient_or_404
from app.schemas import CatalogueMedication, MedicationUseCreate, MedicationUseRead, MedicationUseUpdate
from app.proposals import MedicationRuleProposal
from app.validation import medication_date_errors, raise_if_invalid

router = APIRouter()


def get_use_or_404(session: Session, patient_id: int, use_id: int) -> MedicationUse:
    use = session.get(MedicationUse, use_id)
    if use is None or use.patient_id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Medication use {use_id} not found for patient {patient_id}")
    return use


@router.get("/medications", response_model=list[CatalogueMedication], tags=["Medication catalogue"])
def list_catalogue(request: Request) -> list[CatalogueMedication]:
    return list(request.app.state.catalogue.values())


@router.get("/medications/{medication_id}", response_model=CatalogueMedication, tags=["Medication catalogue"])
def read_catalogue_medication(medication_id: str, request: Request) -> CatalogueMedication:
    medication = request.app.state.catalogue.get(medication_id)
    if medication is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Medication '{medication_id}' is not in the catalogue")
    return medication


@router.post(
    "/patients/{patient_id}/medications",
    response_model=MedicationUseRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Medication use"],
)
def add_medication_use(patient_id: int, body: MedicationUseCreate, request: Request, session: SessionDep) -> MedicationUse:
    patient = get_patient_or_404(session, patient_id)
    entry = request.app.state.catalogue.get(body.medication_id)
    if entry is None:
        raise_if_invalid({"medication_id": f"'{body.medication_id}' is not in the medication catalogue"})
    if entry.status == "archived":
        # Existing uses of archived entries are kept; only new ones are refused.
        raise_if_invalid({"medication_id": f"'{body.medication_id}' is archived: outside the current medication scope (metformin and ACE inhibitors)"})
    raise_if_invalid(medication_date_errors(body.start_date, body.last_dose_change_date, patient.date_of_birth))

    use = MedicationUse(patient_id=patient_id, **body.model_dump())
    session.add(use)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Patient {patient_id} already has '{body.medication_id}'. Update that record instead.",
        )
    session.refresh(use)
    return use


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationUseRead], tags=["Medication use"])
def list_medication_uses(patient_id: int, session: SessionDep) -> list[MedicationUse]:
    get_patient_or_404(session, patient_id)
    return session.exec(select(MedicationUse).where(MedicationUse.patient_id == patient_id)).all()


@router.patch("/patients/{patient_id}/medications/{use_id}", response_model=MedicationUseRead, tags=["Medication use"])
def update_medication_use(patient_id: int, use_id: int, body: MedicationUseUpdate, session: SessionDep) -> MedicationUse:
    patient = get_patient_or_404(session, patient_id)
    use = get_use_or_404(session, patient_id, use_id)
    changes = body.model_dump(exclude_unset=True)
    merged = use.model_dump() | changes
    raise_if_invalid(medication_date_errors(merged["start_date"], merged["last_dose_change_date"], patient.date_of_birth))

    use.sqlmodel_update(changes)
    session.add(use)
    session.commit()
    session.refresh(use)
    return use


@router.delete("/patients/{patient_id}/medications/{use_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Medication use"])
def remove_medication_use(patient_id: int, use_id: int, session: SessionDep) -> None:
    get_patient_or_404(session, patient_id)
    session.delete(get_use_or_404(session, patient_id, use_id))
    session.commit()


class MedicationScopeRead(BaseModel):
    active_medication_ids: list[str]
    archived_medication_ids: list[str]
    active_rule_ids: list[str]
    archived_rule_ids: list[str]
    proposal_ids: list[str]
    note: str = (
        "Medication monitoring is limited to metformin and ACE inhibitors. Archived entries stay readable so recorded "
        "uses keep their names; their rules are kept but not evaluated."
    )


@router.get("/medication-scope", response_model=MedicationScopeRead, tags=["Medication catalogue"])
def read_medication_scope(request: Request) -> MedicationScopeRead:
    catalogue, rule_set = request.app.state.catalogue, request.app.state.rule_set
    medication_rules = [rule for rule in rule_set.rules if rule.track == "medication"]
    return MedicationScopeRead(
        active_medication_ids=[m.id for m in catalogue.values() if m.status == "active"],
        archived_medication_ids=[m.id for m in catalogue.values() if m.status == "archived"],
        active_rule_ids=[rule.id for rule in medication_rules if rule.lifecycle == "active"],
        archived_rule_ids=[rule.id for rule in medication_rules if rule.lifecycle == "archived"],
        proposal_ids=[proposal.id for proposal in request.app.state.proposals],
    )


@router.get(
    "/medication-rule-proposals",
    response_model=list[MedicationRuleProposal],
    tags=["Medication catalogue"],
    description="Draft monitoring proposals from the evidence PDFs, for clinical review. Never evaluated and never scheduled.",
)
def list_medication_rule_proposals(request: Request) -> list[MedicationRuleProposal]:
    return list(request.app.state.proposals)
