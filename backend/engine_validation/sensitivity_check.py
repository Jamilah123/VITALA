"""Check that the validation harness detects real defects (mutation testing).

Each mutation patches the engine in memory only; no rule file or database is changed.
A useful harness must turn some cases from pass to fail for every mutation.

    .\\.venv\\Scripts\\python.exe -m engine_validation.sensitivity_check
"""

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path

import app.main
import app.risk_inputs as risk_inputs
import app.screening as screening
from app.models import DiabetesType
from engine_validation.run_validation import DATASET, RESULTS, evaluate_case


@contextmanager
def reactivate_archived_rules():
    original = app.main.load_rule_set

    def full_scope(catalogue):
        rule_set = original(catalogue)
        rules = tuple(r.model_copy(update={"lifecycle": "active", "archived_on": None, "archive_reason_ar": None}) for r in rule_set.rules)
        return replace(rule_set, rules=rules, archived_medication_ids=frozenset())

    app.main.load_rule_set = full_scope
    try:
        yield
    finally:
        app.main.load_rule_set = original


@contextmanager
def assume_diabetes_type_when_unknown():
    # Adding "unknown" to a rule's allowed types is NOT enough to break the engine,
    # because _check_eligibility tests for unknown before the type list (an equivalent mutant).
    # This mutation instead makes the eligibility check read an unknown type as type 2.
    original = screening._check_eligibility

    def assume_type_2(rule, criteria, patient, known, today, risk=risk_inputs.EMPTY_RISK_CONTEXT):
        if patient.diabetes_type == DiabetesType.unknown:
            patient = patient.model_copy(update={"diabetes_type": DiabetesType.type_2})
        return original(rule, criteria, patient, known, today, risk)

    screening._check_eligibility = assume_type_2
    try:
        yield
    finally:
        screening._check_eligibility = original


@contextmanager
def approve_unreviewed_risk_mapping():
    defaults = risk_inputs.build_risk_context.__defaults__
    approved = tuple(replace(m, status="approved", reviewer="MUTATION", reviewed_on=date(2026, 11, 14)) for m in risk_inputs.RISK_INPUT_MAPPINGS)
    risk_inputs.build_risk_context.__defaults__ = defaults[:-1] + (approved,)
    try:
        yield
    finally:
        risk_inputs.build_risk_context.__defaults__ = defaults


MUTATIONS = {
    "reactivate_archived_medication_rules": reactivate_archived_rules,
    "assume_diabetes_type_when_unknown": assume_diabetes_type_when_unknown,
    "approve_unreviewed_risk_mapping": approve_unreviewed_risk_mapping,
}


def main() -> None:
    cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    sources = {s["id"] for s in json.loads((Path(__file__).resolve().parents[1] / "data" / "sources.json").read_text(encoding="utf-8"))}
    report = {}
    for name, mutation in MUTATIONS.items():
        with mutation():
            failed = [(r["case_id"], r["failure_reasons"]) for r in (evaluate_case(c, sources) for c in cases) if not r["overall_pass"]]
        report[name] = {"detected": bool(failed), "failing_cases": [c for c, _ in failed],
                        "example_reasons": sorted({reason for _, reasons in failed for reason in reasons})[:6]}
        print(f"{name}: {'DETECTED' if failed else 'NOT DETECTED'} -> {[c for c, _ in failed]}")
    # the unmutated engine must pass again afterwards
    clean = [evaluate_case(c, sources)["overall_pass"] for c in cases]
    report["unmutated_rerun_all_pass"] = all(clean)
    print("unmutated rerun all pass:", all(clean))
    (RESULTS / "sensitivity_check.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
