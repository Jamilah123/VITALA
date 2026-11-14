"""Run the 25 synthetic engine scenarios against the current VITALA backend.

Usage (from the backend folder):
    .\\.venv\\Scripts\\python.exe -m engine_validation.run_validation

Every case runs in its own temporary SQLite database, through the public API
(TestClient), except two steps the API cannot express: linking the patient to a
demo clinic appointment (to read the clinician summary) and inserting a
historical prescription of an archived medicine after the API has refused it.
The real vitala.db, the rule files and the dataset are never written.

Two separate label comparisons are made:
  * baseline: actual focus-rule status vs the dataset's provisional label, which
    was inferred from the pre-integration code.
  * gate: the dataset's post-update requirement (expected_post_update_gate).
Clinician concordance cannot be computed: clinician_gold_label is blank.
"""

import csv
import json
import statistics
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import Settings
from app.main import create_app
from app.models import Appointment, AppointmentStatus, BookingSource, Clinic, ClinicPatient, Doctor, MedicationUse

HERE = Path(__file__).resolve().parent
DATASET = HERE / "dataset" / "cases.json"
RESULTS = HERE / "results"
REPEATS = 5  # timed repetitions of each read

RISK_GATES = {
    "no_unapproved_risk_recommendation",
    "store_display_no_unapproved_cancer_rule",
    "store_display_no_unapproved_genetic_rule",
    "record_risk_factors_no_new_unapproved_rules",
    "allergy_display_only_and_preserve_unknown",
}
CONFIRMATION = {"patient_reported": "patient_reported", "patient_reported_unverified": "patient_reported",
                "clinically_confirmed": "clinically_confirmed", "confirmed": "clinically_confirmed"}
CHRONIC = {"type_1_diabetes", "type_2_diabetes", "diabetes_type_unknown", "hypertension", "coronary_heart_disease",
           "heart_failure", "stroke", "chronic_kidney_disease", "high_cholesterol", "obesity", "asthma", "copd"}
DIMENSIONS = {  # case -> evaluation dimensions
    **{f"VIT-{n:02d}": ["diabetes"] for n in range(1, 7)},
    **{f"VIT-{n:02d}": ["hypertension"] for n in range(7, 12)},
    "VIT-12": ["metformin"], "VIT-13": ["metformin"], "VIT-18": ["metformin"],
    **{f"VIT-{n}": ["ace_inhibitors"] for n in (14, 15, 16, 17)},
    "VIT-19": ["medication_exclusion"], "VIT-20": ["medication_exclusion"],
    **{f"VIT-{n}": ["risk_factors"] for n in (21, 22, 23, 24)},
    "VIT-25": ["risk_factors", "allergies"],
}
MISSING_DATA_CASES = {"VIT-04", "VIT-06", "VIT-07", "VIT-09", "VIT-10", "VIT-11", "VIT-17", "VIT-25"}
for case_id in MISSING_DATA_CASES:
    DIMENSIONS[case_id] = DIMENSIONS[case_id] + ["missing_data"]


def timed(fn, repeats=1):
    times, result = [], None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - start) * 1000)
    return result, times


def walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item)


class CaseRun:
    def __init__(self, case: dict, workdir: Path, with_extras: bool = True):
        self.case, self.with_extras = case, with_extras
        self.settings = Settings(_env_file=None, database_path=workdir / "case.db", backup_dir=workdir / "backups")
        self.notes: list[str] = []
        self.load_errors: list[str] = []
        self.archived_refusals: list[str] = []
        self.historical_inserted: list[str] = []

    def load(self, client: TestClient) -> int:
        case = self.case
        response = client.post("/patients", json=case["patient"])
        if response.status_code != 201:
            raise RuntimeError(f"patient load failed: {response.status_code} {response.text}")
        pid = response.json()["id"]
        if self.with_extras:
            response = client.post(f"/patients/{pid}/risk-profile", json=case["risk_profile"])
            if response.status_code != 201:
                self.load_errors.append(f"risk-profile {response.status_code}: {response.text[:200]}")
        for use in case["medication_uses"]:
            response = client.post(f"/patients/{pid}/medications", json=use)
            if response.status_code == 201:
                continue
            if response.status_code == 422 and "archived" in response.text:
                # New uses of archived medicines are refused by design. The scenario is a historical
                # prescription, so it is stored the way pre-existing records are: unchanged, directly.
                self.archived_refusals.append(use["medication_id"])
                with Session(client.app.state.engine) as session:
                    session.add(MedicationUse(patient_id=pid, medication_id=use["medication_id"], dose_text=use["dose_text"],
                                              start_date=date.fromisoformat(use["start_date"]) if use.get("start_date") else None))
                    session.commit()
                self.historical_inserted.append(use["medication_id"])
            else:
                self.load_errors.append(f"medication {use['medication_id']} {response.status_code}: {response.text[:200]}")
        for record in case["screening_records"]:
            response = client.post(f"/patients/{pid}/screening-records", json=record)
            if response.status_code != 201:
                self.load_errors.append(f"screening record {response.status_code}")
        if self.with_extras:
            self._load_history(client, pid)
        return pid

    def _load_history(self, client: TestClient, pid: int) -> None:
        extra = self.case["additional_medical_history"]
        base = f"/patients/{pid}"
        for allergy in extra.get("allergies", []):
            body = {"allergen": allergy["allergen"], "reaction": allergy.get("reaction"),
                    "severity": allergy.get("severity", "unknown"),
                    "verification": CONFIRMATION.get(allergy.get("confirmation_status"), "unknown")}
            self._check(client.post(f"{base}/allergies", json=body), "allergy")
        relatives: dict[str, int] = {}
        for item in extra.get("family_cancer_history", []):
            key = item.get("relative_key") or f"{item['relationship']}-{len(relatives)}"
            if key not in relatives:
                created = client.post(f"{base}/family-history/relatives", json={"relationship": item["relationship"], "label": key})
                self._check(created, "relative")
                relatives[key] = created.json()["id"]
            body = {"category": "cancer", "condition": item["cancer_type"], "age_at_diagnosis": item.get("age_at_diagnosis"),
                    "verification": CONFIRMATION.get(item.get("information_source"), "unknown")}
            self._check(client.post(f"{base}/family-history/relatives/{relatives[key]}/conditions", json=body), "cancer condition")
        for item in extra.get("family_chronic_autoimmune_history", []):
            category = "chronic" if item["condition"] in CHRONIC else "autoimmune"
            body = {"relationship": item["relationship"], "conditions": [
                {"category": category, "condition": item["condition"], "age_at_diagnosis": item.get("diagnosed_age"),
                 "verification": CONFIRMATION.get(item.get("confirmation_status"), "unknown")}]}
            self._check(client.post(f"{base}/family-history/relatives", json=body), "chronic/autoimmune relative")
        for item in extra.get("genetic_mutations", []):
            body = {"name": f"{item['gene']} variant ({item.get('variant', 'unspecified')})", "gene": item["gene"],
                    "verification": CONFIRMATION.get(item.get("confirmation_status"), "unknown")}
            self._check(client.post(f"{base}/genetic-findings", json=body), "genetic finding")

    def _check(self, response, label):
        if response.status_code not in (200, 201):
            self.load_errors.append(f"{label} {response.status_code}: {response.text[:200]}")

    @staticmethod
    def link_to_clinic(client: TestClient, pid: int) -> tuple[int, int]:
        """Test fixture: the API has no endpoint to link a patient to a clinic, so do it directly."""
        with Session(client.app.state.engine) as session:
            clinic = Clinic(name_ar="عيادة اختبار", is_demo=True)
            session.add(clinic)
            session.flush()
            doctor = Doctor(clinic_id=clinic.id, name_ar="طبيب اختبار")
            link = ClinicPatient(clinic_id=clinic.id, patient_id=pid, display_name_ar="مريض اختبار")
            session.add_all([doctor, link])
            session.flush()
            appointment = Appointment(clinic_id=clinic.id, doctor_id=doctor.id, clinic_patient_id=link.id,
                                      scheduled_at=datetime.now(timezone.utc) + timedelta(days=3),
                                      status=AppointmentStatus.scheduled, booking_source=BookingSource.clinic)
            session.add(appointment)
            session.commit()
            return clinic.id, appointment.id


def statuses(preview: dict) -> dict:
    return {a["rule_id"]: (a["status"], tuple(a["reasons"])) for a in preview["actions"]}


def evaluate_case(case: dict, sources: dict) -> dict:
    labels = case["labels"]
    focus, expected, gate = labels["focus_rule_id"], labels["provisional_expected_current_engine_status"], labels["expected_post_update_gate"]
    with tempfile.TemporaryDirectory() as tmp:
        run = CaseRun(case, Path(tmp))
        with TestClient(create_app(run.settings)) as client:
            pid, load_ms = timed(lambda: run.load(client))
            preview, preview_ms = timed(lambda: client.get(f"/patients/{pid}/screening-preview").json(), REPEATS)
            summary, summary_ms = timed(lambda: client.get(f"/patients/{pid}/screening-summary").json(), REPEATS)
            history = client.get(f"/patients/{pid}/medical-history").json()
            medications = client.get(f"/patients/{pid}/medications").json()
            clinic_id, appointment_id = CaseRun.link_to_clinic(client, pid)
            clinician, clinician_ms = timed(lambda: client.get(f"/clinics/{clinic_id}/appointments/{appointment_id}/summary"), REPEATS)
            clinician_status, clinician = clinician.status_code, clinician.json()
            scope = client.get("/medication-scope").json()

    control = None
    if gate in RISK_GATES:
        with tempfile.TemporaryDirectory() as tmp:
            control_run = CaseRun(case, Path(tmp), with_extras=False)
            with TestClient(create_app(control_run.settings)) as client:
                control_pid = control_run.load(client)
                control = client.get(f"/patients/{control_pid}/screening-preview").json()

    actions = {a["rule_id"]: a for a in preview["actions"]}
    action = actions.get(focus)
    actual = action["status"] if action else ("archived_not_evaluated" if focus in scope["archived_rule_ids"] else "absent")

    # ---- universal safety safeguards
    all_actions = preview["actions"] + [r for t in summary["tests"] for r in t["rules"]]
    keys = set(walk_keys(preview)) | set(walk_keys(summary))
    safety = {
        "auto_schedule_disabled": preview["auto_schedule_enabled"] is False and summary["auto_schedule_enabled"] is False
        and all(a["auto_schedule_enabled"] is False for a in all_actions),
        "not_clinically_approved": preview["clinically_approved"] is False and summary["clinically_approved"] is False,
        "all_rules_draft": all(a["review_status"] == "draft_not_clinician_reviewed" for a in all_actions),
        "no_due_dates": not keys & {"due_date", "next_due_date", "scheduled_for", "interval_days"},
        "no_archived_rule_evaluated": not set(actions) & set(scope["archived_rule_ids"]),
        "no_proposal_evaluated": not any(r.startswith("MRP") for r in actions),
        "unknown_never_negative": all(not any("unknown" in reason for reason in a["reasons"]) for a in preview["actions"]),
        "no_actionable_risk_factor": not any(f["actionable"] for f in preview["risk_factors"]),
        "preview_matches_summary": statuses(preview) == {r["rule_id"]: (r["status"], tuple(r["reasons"])) for t in summary["tests"] for r in t["rules"]},
        "clinician_summary_ok": clinician_status == 200 and clinician.get("clinically_validated") is False and clinician.get("medical_history") is not None,
        "load_without_errors": not run.load_errors,
    }

    # ---- traceability of the focus rule
    trace_sources = action["sources"] if action else []
    traceability = {
        "focus_rule_has_sources": bool(trace_sources),
        "sources_resolve": all(s["source_id"] in sources for s in trace_sources) if trace_sources else False,
        "locators_present": all(s["locator"].strip() for s in trace_sources) if trace_sources else False,
        "urls_present": all(s["url"].startswith("http") for s in trace_sources) if trace_sources else False,
        "review_status_present": bool(action and action["review_status"]),
        "schedule_text_present": bool(action and action["schedule_text_ar"]),
    }
    traceable = all(traceability.values())

    # ---- baseline vs gate
    baseline_match = actual == expected
    gate_checks: dict[str, bool] = {}
    if gate == "existing_logic":
        gate_checks["focus_status_matches_label"] = baseline_match
    elif gate == "exclude_out_of_scope_medication_rules":
        med_ids = [u["medication_id"] for u in case["medication_uses"]]
        stored = {(m["medication_id"], m["dose_text"]) for m in medications}
        gate_checks = {
            "new_use_refused_by_api": run.archived_refusals == med_ids,
            "historical_prescription_intact": all((u["medication_id"], u["dose_text"]) in stored for u in case["medication_uses"]),
            "focus_rule_not_candidate": actual != "candidate",
            "no_medication_candidate": not any(a["track"] == "medication" and a["status"] == "candidate" for a in preview["actions"]),
            "listed_as_out_of_scope": sorted(m["medication_id"] for m in preview["out_of_scope_medications"]) == sorted(med_ids),
            "clinician_summary_marks_archived": all(m["catalogue_status"] == "archived" for m in clinician["medications"]),
        }
    elif gate in RISK_GATES:
        facts = {f["field"]: f for f in history["risk_factors"]}
        extra = case["additional_medical_history"]
        gate_checks = {
            "focus_status_matches_label": baseline_match,
            "statuses_identical_to_control_without_extras": statuses(preview) == statuses(control),
            "no_risk_factor_actionable": not any(f["actionable"] for f in history["risk_factors"]),
            "unknown_profile_values_stay_unknown": all(
                facts[name]["state"] == "unknown" for name, value in case["risk_profile"].items() if value in ("unknown", None) and name in facts
                and not (name.startswith("family_") and extra.get("family_cancer_history"))
            ),
            "shown_in_clinician_summary": clinician.get("medical_history") == history,
        }
        if extra.get("allergies"):
            gate_checks["allergies_stored"] = [a["allergen"] for a in history["allergies"]] == [a["allergen"] for a in extra["allergies"]]
        if extra.get("family_cancer_history"):
            keys_ = {i.get("relative_key") for i in extra["family_cancer_history"]}
            gate_checks["cancer_relatives_counted_once"] = history["family_counts"]["relatives_with_cancer"] == len(keys_)
            gate_checks["cancer_fact_present"] = facts["family_cancer_history"]["state"] == "present"
        if extra.get("family_chronic_autoimmune_history"):
            gate_checks["chronic_autoimmune_stored"] = history["family_counts"]["relatives_with_chronic_or_autoimmune"] == len(extra["family_chronic_autoimmune_history"])
        if extra.get("genetic_mutations"):
            gate_checks["genetic_stored_unconfirmed"] = bool(history["genetic_findings"]) and all(
                g["verification"] != "clinically_confirmed" for g in history["genetic_findings"])
        smoking = case["risk_profile"].get("smoking_status")
        if smoking and smoking != "unknown":
            gate_checks["smoking_recorded_as_present"] = facts["smoking_status"]["state"] == ("absent" if smoking == "never" else "present")
    else:
        gate_checks["unknown_gate"] = False
    gate_pass = all(gate_checks.values())

    failures = [f"gate:{k}" for k, v in gate_checks.items() if not v] + [f"safety:{k}" for k, v in safety.items() if not v]
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "scenario": case["scenario"],
        "dimensions": DIMENSIONS[case["case_id"]],
        "focus_rule_id": focus,
        "expected_post_update_gate": gate,
        "provisional_expected_status": expected,
        "actual_status": actual,
        "actual_reasons": action["reasons"] if action else [],
        "deciding_missing_inputs": [m["field"] for m in action["missing_inputs"] if m["affects_eligibility"]] if action else [],
        "other_missing_inputs": [f"{m['field']}({m['reason']})" for m in action["missing_inputs"] if not m["affects_eligibility"]] if action else [],
        "matched_medication_ids": action["matched_medication_ids"] if action else [],
        "auto_schedule_enabled": action["auto_schedule_enabled"] if action else False,
        "review_status": action["review_status"] if action else None,
        "source_ids": [s["source_id"] for s in trace_sources],
        "source_locators": [f"{s['source_id']}: {s['locator']}" for s in trace_sources],
        "conflict_ids": action["conflict_ids"] if action else [],
        "baseline_label_match": baseline_match,
        "gate_checks": gate_checks,
        "gate_pass": gate_pass,
        "safety_checks": safety,
        "safety_pass": all(safety.values()),
        "traceability_checks": traceability,
        "traceable": traceable,
        "overall_pass": gate_pass and all(safety.values()),
        "failure_reasons": failures,
        "archived_refused_by_api": run.archived_refusals,
        "historical_inserted": run.historical_inserted,
        "load_errors": run.load_errors,
        "timing_ms": {
            "load_via_api": load_ms[0],
            "preview_median": statistics.median(preview_ms),
            "preview_all": preview_ms,
            "summary_median": statistics.median(summary_ms),
            "clinician_summary_median": statistics.median(clinician_ms),
        },
        "explanation_from_dataset": labels["expected_current_behavior_explanation"],
        "clinician_gold_label": labels["clinician_gold_label"],
    }


def main() -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) == 25 == data["metadata"]["total_cases"], "dataset must contain 25 cases"
    sources = {s["id"] for s in json.loads((Path(__file__).resolve().parents[1] / "data" / "sources.json").read_text(encoding="utf-8"))}
    RESULTS.mkdir(exist_ok=True)

    started = time.perf_counter()
    results = []
    for case in cases:
        result = evaluate_case(case, sources)
        results.append(result)
        mark = "PASS" if result["overall_pass"] else "FAIL"
        print(f"{result['case_id']} {mark:4} focus={result['focus_rule_id']:6} expected={result['provisional_expected_status']:17} "
              f"actual={result['actual_status']:22} gate={result['expected_post_update_gate']} {result['failure_reasons'] or ''}")
    total_s = time.perf_counter() - started

    (RESULTS / "engine_validation_results.json").write_text(
        json.dumps({"run_at": datetime.now(timezone.utc).isoformat(), "total_seconds": total_s, "python": sys.version.split()[0],
                    "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    columns = ["case_id", "category", "scenario", "focus_rule_id", "expected_post_update_gate", "provisional_expected_status",
               "actual_status", "baseline_label_match", "gate_pass", "safety_pass", "traceable", "overall_pass", "failure_reasons",
               "actual_reasons", "deciding_missing_inputs", "other_missing_inputs", "matched_medication_ids", "auto_schedule_enabled",
               "review_status", "source_locators", "conflict_ids", "archived_refused_by_api", "load_errors",
               "preview_median_ms", "load_via_api_ms", "clinician_gold_label"]
    with open(RESULTS / "engine_validation_results.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for r in results:
            row = {k: r.get(k) for k in columns}
            row["preview_median_ms"] = round(r["timing_ms"]["preview_median"], 2)
            row["load_via_api_ms"] = round(r["timing_ms"]["load_via_api"], 2)
            for k, v in row.items():
                if isinstance(v, list):
                    row[k] = "; ".join(map(str, v))
            writer.writerow(row)
    passed = sum(r["overall_pass"] for r in results)
    print(f"\n{passed}/{len(results)} cases passed overall in {total_s:.1f} s")


if __name__ == "__main__":
    main()
