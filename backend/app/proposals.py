"""Draft medication-monitoring proposals derived from the attached evidence PDFs.

Proposals are a review queue for the medical team, not rules. The engine never
evaluates them: they are loaded only to validate their references and to show
them through the API. A proposal that claims to be executable, schedules
anything, or has a reviewer stops the app at startup. Turning one into a rule
requires a clinician, a new entry in medication_monitoring.json and criteria.py,
and the usual tests.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.rules import DATA_DIR, RuleSet
from app.schemas import CatalogueMedication
from app.screening_tests import SCREENING_TESTS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StatedTiming(_Strict):
    text_en: str
    source_id: str
    locator: str


class MedicationRuleProposal(_Strict):
    id: str
    topic: str
    drug_ids: list[str] = Field(min_length=1)
    proposed_action_id: str
    related_rule_ids: list[str]
    proposed_eligibility_en: str
    proposed_eligibility_ar: str
    timing_as_stated: list[StatedTiming] = Field(min_length=1)
    required_inputs: list[str]
    inputs_vitala_collects: list[str]
    inputs_not_collected: list[str]
    missing_input_behavior: Literal["needs_information"]
    conflicts_en: list[str]
    why_not_executable_en: str
    review_status: Literal["pending_clinical_review", "not_suitable_for_rule"]
    executable: Literal[False]
    auto_schedule_enabled: Literal[False]
    reviewer: None
    reviewed_on: None
    collection_notes_en: str | None = None


def load_proposals(
    rule_set: RuleSet,
    catalogue: dict[str, CatalogueMedication],
    path: Path = DATA_DIR / "medication_rule_proposals.json",
) -> tuple[MedicationRuleProposal, ...]:
    proposals = TypeAdapter(list[MedicationRuleProposal]).validate_json(path.read_text(encoding="utf-8"))
    rule_ids = {rule.id for rule in rule_set.rules}
    errors: list[str] = []
    ids = [proposal.id for proposal in proposals]
    if len(ids) != len(set(ids)):
        errors.append("duplicate proposal ids")
    for proposal in proposals:
        for drug_id in proposal.drug_ids:
            entry = catalogue.get(drug_id)
            if entry is None or entry.status != "active":
                errors.append(f"{proposal.id}: {drug_id} is not an active catalogue medication")
        if proposal.proposed_action_id not in SCREENING_TESTS:
            errors.append(f"{proposal.id}: unknown test {proposal.proposed_action_id}")
        errors += [f"{proposal.id}: unknown rule {rule_id}" for rule_id in proposal.related_rule_ids if rule_id not in rule_ids]
        errors += [
            f"{proposal.id}: unknown source {timing.source_id}" for timing in proposal.timing_as_stated if timing.source_id not in rule_set.sources
        ]
        declared = set(proposal.inputs_vitala_collects) | set(proposal.inputs_not_collected)
        if declared != set(proposal.required_inputs) or set(proposal.inputs_vitala_collects) & set(proposal.inputs_not_collected):
            errors.append(f"{proposal.id}: every required input must be listed once as collected or not collected")
    if errors:
        raise ValueError("Invalid medication rule proposals: " + "; ".join(errors))
    return tuple(proposals)
