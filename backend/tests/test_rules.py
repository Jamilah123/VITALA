import json
import shutil

import pytest

from app.catalogue import load_catalogue
from app.rules import DATA_DIR, load_rule_set
from app.criteria import check_criteria_cover

RULE_FILES = ["disease_rules.json", "medication_monitoring.json", "sources.json", "conflicts.json", "explanation_knowledge.json"]


@pytest.fixture
def catalogue():
    return load_catalogue(DATA_DIR / "medications.json")


def changed_copy(tmp_path, name, change):
    for file_name in RULE_FILES:
        shutil.copy(DATA_DIR / file_name, tmp_path / file_name)
    records = json.loads((tmp_path / name).read_text(encoding="utf-8"))
    change(records)
    (tmp_path / name).write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_loads_every_research_rule_and_source(catalogue):
    rule_set = load_rule_set(catalogue)
    metadata = json.loads((DATA_DIR / "metadata.json").read_text(encoding="utf-8"))["counts"]

    tracks = [rule.track for rule in rule_set.rules]
    assert tracks.count("diabetes") == metadata["diabetes_rules"]
    assert tracks.count("hypertension") == metadata["hypertension_rules"]
    assert tracks.count("medication") == metadata["medication_rules"]
    assert len(rule_set.sources) == metadata["sources"]


def test_every_rule_has_encoded_eligibility_criteria(catalogue):
    check_criteria_cover(load_rule_set(catalogue).rules)


@pytest.mark.parametrize(
    ("name", "change", "message"),
    [
        ("disease_rules.json", lambda rules: rules[0]["evidence"].append({"source_id": "S99", "locator": "p. 1"}), "S99"),
        ("disease_rules.json", lambda rules: rules[0].update(evidence=[]), "evidence"),
        ("disease_rules.json", lambda rules: rules[0]["knowledge_ids"].append("K99"), "K99"),
        ("disease_rules.json", lambda rules: rules[0].update(auto_schedule_enabled=True), "auto_schedule_enabled"),
        ("disease_rules.json", lambda rules: rules[0].update(clinical_status="clinician_approved"), "clinical_status"),
        ("disease_rules.json", lambda rules: rules[0].update(reviewer="Synthetic Reviewer"), "reviewer"),
        ("disease_rules.json", lambda rules: rules[0].update(unexpected_field=1), "unexpected_field"),
        ("disease_rules.json", lambda rules: rules[0].pop("required_inputs"), "required_inputs"),
        ("disease_rules.json", lambda rules: rules[0].update(track="oncology"), "track"),
        ("disease_rules.json", lambda rules: rules.append(rules[0]), "Duplicate rule"),
        ("medication_monitoring.json", lambda rules: rules[0]["drug_ids"].append("aspirin"), "aspirin"),
        ("medication_monitoring.json", lambda rules: rules[2]["drug_ids"].remove("hydrochlorothiazide"), "hydrochlorothiazide"),
        ("medication_monitoring.json", lambda rules: rules[0].update(track="diabetes"), "drug_ids"),
        ("sources.json", lambda sources: sources.append(sources[0]), "Duplicate source"),
        ("conflicts.json", lambda conflicts: conflicts[0]["rule_ids"].append("DM99"), "DM99"),
        ("conflicts.json", lambda conflicts: conflicts[0]["source_ids"].append("S99"), "S99"),
    ],
)
def test_loader_rejects_invalid_rules_and_broken_references(tmp_path, catalogue, name, change, message):
    data_dir = changed_copy(tmp_path, name, change)

    with pytest.raises(ValueError, match=message):
        load_rule_set(catalogue, data_dir)


def test_new_rule_without_eligibility_criteria_stops_startup(tmp_path, catalogue):
    data_dir = changed_copy(tmp_path, "disease_rules.json", lambda rules: rules.append(rules[0] | {"id": "DM99"}))
    rules = load_rule_set(catalogue, data_dir).rules

    with pytest.raises(ValueError, match="DM99"):
        check_criteria_cover(rules)
