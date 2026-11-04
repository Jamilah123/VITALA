"""Load the research rule files and check every reference between them.

A malformed file or a broken reference stops the app at startup.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.config import BACKEND_DIR
from app.schemas import CatalogueMedication, SourceLocator

DATA_DIR = BACKEND_DIR / "data"


class DataRecord(BaseModel):
    # A field the loader does not know must fail rather than be silently dropped.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Schedule(DataRecord):
    kind: str
    text_ar: str
    unit: Literal["weeks", "months", "years"] | None
    value: int | None
    min: int | None
    max: int | None
    anchor: str | None


class Rule(DataRecord):
    id: str
    track: Literal["diabetes", "hypertension", "medication"]
    action_id: str
    action_name_ar: str
    eligibility_ar: str
    schedule: Schedule
    evidence: list[SourceLocator] = Field(min_length=1)
    required_inputs: list[str]
    notes_ar: str
    review_flags: list[str]
    knowledge_ids: list[str]
    # Only unreviewed drafts load. Approving a rule needs a review workflow in
    # code first, not an edit to the data files.
    clinical_status: Literal["draft_not_clinician_reviewed"]
    auto_schedule_enabled: Literal[False]
    reviewer: None
    reviewed_on: None
    drug_ids: list[str] = []

    @model_validator(mode="after")
    def drug_ids_match_track(self) -> "Rule":
        if (self.track == "medication") != bool(self.drug_ids):
            raise ValueError("drug_ids are required for medication rules and only for them")
        return self


class Source(DataRecord):
    id: str
    title: str
    url: str
    issuer: str
    host: str
    version: str | None
    verified_on: date
    locator: str
    limitation_ar: str


class Conflict(DataRecord):
    id: str
    topic: str
    rule_ids: list[str]
    source_ids: list[str]
    finding_ar: str
    resolution: str | None


class KnowledgeItem(BaseModel):
    id: str


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
    sources: dict[str, Source]
    conflicts: tuple[Conflict, ...]


def _read[T](path: Path, model: type[T]) -> list[T]:
    return TypeAdapter(list[model]).validate_json(path.read_text(encoding="utf-8"))


def _unique_ids(records: Iterable[BaseModel], label: str) -> set[str]:
    ids = [record.id for record in records]
    duplicates = sorted({record_id for record_id in ids if ids.count(record_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {label} ids: {duplicates}")
    return set(ids)


def _require_known(referenced: Iterable[str], known: set[str], owner: str) -> None:
    unknown = sorted(set(referenced) - known)
    if unknown:
        raise ValueError(f"{owner} references unknown ids: {unknown}")


def load_rule_set(catalogue: dict[str, CatalogueMedication], data_dir: Path = DATA_DIR) -> RuleSet:
    rules = _read(data_dir / "disease_rules.json", Rule) + _read(data_dir / "medication_monitoring.json", Rule)
    sources = _read(data_dir / "sources.json", Source)
    conflicts = _read(data_dir / "conflicts.json", Conflict)
    knowledge = _read(data_dir / "explanation_knowledge.json", KnowledgeItem)

    rule_ids = _unique_ids(rules, "rule")
    source_ids = _unique_ids(sources, "source")
    knowledge_ids = _unique_ids(knowledge, "knowledge")
    _unique_ids(conflicts, "conflict")

    for rule in rules:
        _require_known((item.source_id for item in rule.evidence), source_ids, f"Rule {rule.id} evidence")
        _require_known(rule.knowledge_ids, knowledge_ids, f"Rule {rule.id} knowledge_ids")
        _require_known(rule.drug_ids, set(catalogue), f"Rule {rule.id} drug_ids")

    for conflict in conflicts:
        _require_known(conflict.rule_ids, rule_ids, f"Conflict {conflict.id}")
        _require_known(conflict.source_ids, source_ids, f"Conflict {conflict.id}")

    for medication in catalogue.values():
        _require_known((item.source_id for item in medication.identity_evidence), source_ids, f"Medication {medication.id}")
        linked = sorted(rule.id for rule in rules if medication.id in rule.drug_ids)
        if sorted(medication.monitoring_rule_ids) != linked:
            raise ValueError(
                f"Medication {medication.id} lists rules {sorted(medication.monitoring_rule_ids)}, "
                f"but the rule files link it to {linked}"
            )

    return RuleSet(tuple(rules), {source.id: source for source in sources}, tuple(conflicts))
