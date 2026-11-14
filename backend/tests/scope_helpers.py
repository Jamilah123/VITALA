"""Rule-set helpers for engine tests.

full_scope_rule_set() is the real rule data with the 2026-11-14 medication
archive lifted. Engine mechanics (history mappings, eligibility, grouping) do
not depend on which medications are in scope, so their tests keep using every
rule. Tests of the scope change itself use the real, archived rule set.
"""

from dataclasses import replace

from app.catalogue import load_catalogue
from app.rules import DATA_DIR, RuleSet, load_rule_set


def real_rule_set() -> RuleSet:
    return load_rule_set(load_catalogue(DATA_DIR / "medications.json"))


def full_scope_rule_set() -> RuleSet:
    rule_set = real_rule_set()
    rules = tuple(rule.model_copy(update={"lifecycle": "active", "archived_on": None, "archive_reason_ar": None}) for rule in rule_set.rules)
    return replace(rule_set, rules=rules, archived_medication_ids=frozenset())
