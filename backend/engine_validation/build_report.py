"""Build the Markdown report, charts and the medical-team review workbook from the validation results.

Needs matplotlib and openpyxl (not backend dependencies). Run with any Python that has them:
    <python> engine_validation/build_report.py
"""

import json
import statistics
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
DATA = HERE.parent / "data"
STATUSES = ["candidate", "needs_information", "not_applicable", "not_triggered", "archived_not_evaluated"]


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.1f}%)" if d else "n/a"


def kappa(pairs):
    labels = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(ca[l] * cb[l] for l in labels) / n**2
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def static_traceability(rule_id):
    rules = {r["id"]: r for f in ("disease_rules.json", "medication_monitoring.json") for r in json.loads((DATA / f).read_text(encoding="utf-8"))}
    sources = {s["id"] for s in json.loads((DATA / "sources.json").read_text(encoding="utf-8"))}
    rule = rules.get(rule_id)
    if not rule:
        return False, "rule id not found"
    ok = bool(rule["evidence"]) and all(e["source_id"] in sources and e["locator"].strip() for e in rule["evidence"])
    return ok, "; ".join(f"{e['source_id']}: {e['locator']}" for e in rule["evidence"]) + f" (lifecycle: {rule.get('lifecycle', 'active')})"


def main():
    run = json.loads((RESULTS / "engine_validation_results.json").read_text(encoding="utf-8"))
    results = run["results"]
    sensitivity = json.loads((RESULTS / "sensitivity_check.json").read_text(encoding="utf-8"))
    n = len(results)

    baseline = sum(r["baseline_label_match"] for r in results)
    non_scope = [r for r in results if r["expected_post_update_gate"] != "exclude_out_of_scope_medication_rules"]
    baseline_ns = sum(r["baseline_label_match"] for r in non_scope)
    gate = sum(r["gate_pass"] for r in results)
    safety = sum(r["safety_pass"] for r in results)
    overall = sum(r["overall_pass"] for r in results)
    k_all = kappa([(r["provisional_expected_status"], r["actual_status"]) for r in results])
    k_ns = kappa([(r["provisional_expected_status"], r["actual_status"]) for r in non_scope])
    evaluated = [r for r in results if r["actual_status"] != "archived_not_evaluated"]
    runtime_trace = sum(r["traceable"] for r in evaluated)
    static = {r["case_id"]: static_traceability(r["focus_rule_id"]) for r in results}
    static_ok = sum(ok for ok, _ in static.values())
    gold = sum(1 for r in results if r["clinician_gold_label"])
    safety_names = list(results[0]["safety_checks"])
    safety_counts = {name: sum(r["safety_checks"][name] for r in results) for name in safety_names}
    gate_checks_total = sum(len(r["gate_checks"]) for r in results)
    gate_checks_pass = sum(sum(r["gate_checks"].values()) for r in results)
    preview = [r["timing_ms"]["preview_median"] for r in results]
    all_preview = sorted(t for r in results for t in r["timing_ms"]["preview_all"])
    loads = [r["timing_ms"]["load_via_api"] for r in results]
    clin = [r["timing_ms"]["clinician_summary_median"] for r in results]
    p95 = all_preview[int(round(0.95 * (len(all_preview) - 1)))]

    dims = {}
    for r in results:
        for d in r["dimensions"]:
            dims.setdefault(d, []).append(r)

    # ---------------------------------------------------------------- charts
    fig, ax = plt.subplots(figsize=(7, 5))
    exp_labels = [s for s in STATUSES if any(r["provisional_expected_status"] == s for r in results)]
    act_labels = [s for s in STATUSES if any(r["actual_status"] == s for r in results)]
    matrix = [[sum(1 for r in results if r["provisional_expected_status"] == e and r["actual_status"] == a) for a in act_labels] for e in exp_labels]
    ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(act_labels)), act_labels, rotation=30, ha="right")
    ax.set_yticks(range(len(exp_labels)), exp_labels)
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            ax.text(j, i, str(v), ha="center", va="center", color="white" if v > 4 else "black", fontsize=12)
    ax.set_xlabel("Actual engine status (current backend)")
    ax.set_ylabel("Provisional label (pre-integration code)")
    ax.set_title("Focus-rule status: provisional label vs actual (n=25)")
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_status_confusion.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    names = sorted(dims)
    rates = [100 * sum(r["overall_pass"] for r in dims[d]) / len(dims[d]) for d in names]
    bars = ax.bar(names, rates, color="#2f6f8f")
    for bar, d in zip(bars, names):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, f"{sum(r['overall_pass'] for r in dims[d])}/{len(dims[d])}", ha="center")
    ax.set_ylim(0, 110)
    ax.set_ylabel("Cases passing (%)")
    ax.set_title("Pass rate by evaluation dimension (gate + safety)")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_pass_by_dimension.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ids = [r["case_id"] for r in results]
    ax.bar(ids, preview, color="#7a9e3c", label="screening preview (median of 5)")
    ax.plot(ids, clin, "o-", color="#b5532a", label="clinician summary (median of 5)")
    ax.set_ylabel("ms")
    ax.set_title("Execution time per case")
    ax.legend()
    plt.setp(ax.get_xticklabels(), rotation=60, ha="right", fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_execution_time.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(safety_names, [100 * safety_counts[s] / n for s in safety_names], color="#4b4b8f")
    ax.set_xlim(0, 105)
    ax.set_xlabel("Cases where the safeguard held (%)")
    ax.set_title("Safety safeguards across all 25 cases")
    fig.tight_layout()
    fig.savefig(RESULTS / "chart_safety_safeguards.png", dpi=150)
    plt.close(fig)

    # ---------------------------------------------------------------- markdown
    lines = [
        "# VITALA screening engine: 25-case synthetic validation",
        "",
        f"Run: {run['run_at']} · branch `integration/rag-risk-profile-meds-scope` · Python {run['python']} · "
        f"total runtime {run['total_seconds']:.1f} s · temporary SQLite database per case.",
        "",
        "> **Not clinical validation.** The labels are the dataset's *provisional* expectations, inferred from the "
        "pre-integration code. `clinician_gold_label` is blank for all 25 cases, so clinician concordance cannot be computed. "
        "`candidate` means a draft rule matched recorded data. It is not a recommendation.",
        "",
        "## Headline metrics",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Overall pass (post-update gate + every safety safeguard) | **{pct(overall, n)}** |",
        f"| Post-update gate pass | {pct(gate, n)} ({gate_checks_pass}/{gate_checks_total} individual gate checks) |",
        f"| Safety safeguards held in every case | {pct(safety, n)} ({sum(safety_counts.values())}/{n * len(safety_names)} checks) |",
        f"| Agreement with the provisional label, all cases | {pct(baseline, n)}, Cohen's κ = {k_all:.3f} |",
        f"| Agreement with the provisional label, excluding the 2 intentional scope changes | {pct(baseline_ns, len(non_scope))}, κ = {k_ns:.3f} |",
        f"| Runtime traceability (evaluated focus rule → source + locator + URL + review status) | {pct(runtime_trace, len(evaluated))} |",
        f"| Static traceability (focus rule id → rule file → registered source + locator) | {pct(static_ok, n)} |",
        f"| Clinician concordance | not computable: {gold}/{n} gold labels filled |",
        f"| Screening preview latency | median {statistics.median(preview):.1f} ms, p95 {p95:.1f} ms, max {max(all_preview):.1f} ms ({len(all_preview)} calls) |",
        f"| Clinician summary latency | median {statistics.median(clin):.1f} ms, max {max(clin):.1f} ms |",
        f"| Loading one case through the API | median {statistics.median(loads):.1f} ms, max {max(loads):.1f} ms |",
        "",
        "The two label disagreements are **VIT-19** and **VIT-20**. Their provisional labels describe the legacy engine "
        "(losartan → MED05 candidate, atorvastatin → MED07 candidate). The dataset requires them to stop being active "
        "(`exclude_out_of_scope_medication_rules`), and they did: MED05 is `not_triggered` for losartan, and MED07 is "
        "archived and not evaluated. Both prescriptions remain stored unchanged.",
        "",
        "## Results by dimension",
        "",
        "| Dimension | Cases | Pass | Notes |",
        "|---|---|---|---|",
    ]
    notes = {
        "diabetes": "DM01/DM03: type 1 duration, unknown type, not diagnosed",
        "hypertension": "HTN01/03/04: unknown status stays undecided; recorded-but-unapproved pregnancy never applied",
        "metformin": "MED01/MED02 trigger; no metformin → not_triggered",
        "ace_inhibitors": "MED03/04/05 trigger on enalapril/lisinopril; unknown diabetes → needs_information",
        "medication_exclusion": "archived drugs refused by the API, historical record intact, no active rule",
        "risk_factors": "statuses identical to a control run without the data; stored and shown; nothing actionable",
        "missing_data": "unknown values never produce not_applicable",
        "allergies": "stored, shown in the clinician summary, no effect on screening",
    }
    for d in sorted(dims):
        lines.append(f"| {d} | {len(dims[d])} | {pct(sum(r['overall_pass'] for r in dims[d]), len(dims[d]))} | {notes.get(d, '')} |")
    lines += ["", "## Per-case results", "", "| Case | Scenario | Focus | Provisional | Actual | Gate | Safety | Overall | Source |", "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        src = "; ".join(r["source_locators"]) or static[r["case_id"]][1]
        lines.append(f"| {r['case_id']} | {r['scenario']} | {r['focus_rule_id']} | {r['provisional_expected_status']} | {r['actual_status']} | "
                     f"{'✔' if r['gate_pass'] else '✘'} {r['expected_post_update_gate']} | {'✔' if r['safety_pass'] else '✘'} | "
                     f"{'PASS' if r['overall_pass'] else 'FAIL'} | {src} |")
    lines += ["", "## Safety safeguards checked in every case", "", "| Safeguard | Held |", "|---|---|"]
    for s in safety_names:
        lines.append(f"| {s} | {pct(safety_counts[s], n)} |")
    lines += [
        "",
        "## Can the harness fail? (mutation check)",
        "",
        "Each defect was injected in memory into the engine and the 25 cases were rerun. The rule files were not changed.",
        "",
        "| Injected defect | Detected | Cases that failed |",
        "|---|---|---|",
    ]
    for name, item in sensitivity.items():
        if isinstance(item, dict):
            lines.append(f"| {name} | {'yes' if item['detected'] else 'NO'} | {', '.join(item['failing_cases'])} |")
    lines += [
        f"| (unmutated engine rerun) | all pass: {sensitivity['unmutated_rerun_all_pass']} | |",
        "",
        "Adding `unknown` to DM03's allowed diabetes types did *not* change the engine's output: the engine tests for an "
        "unknown type before it checks the type list. That mutation was replaced with one that rewrites an unknown type "
        "as type 2, which VIT-04 catches. Only one case (VIT-04) guards that defect, so coverage of missing-data paths is thin.",
        "",
        "## Method",
        "",
        "* Each case runs against a new temporary database through the public API: patient, risk profile, medications, "
        "allergies, family relatives and conditions, and genetic findings. Two steps have no API and use a test fixture: "
        "linking the patient to a clinic appointment (to read the clinician summary), and storing a historical "
        "prescription of an archived medicine after the API refused it (VIT-19, VIT-20).",
        "* The dataset's `additional_medical_history` shapes were mapped onto the new endpoints: `relative_key` becomes one "
        "relative record, `patient_reported_unverified` becomes `verification: patient_reported`, `diagnosed_age` "
        "becomes `age_at_diagnosis`, and conditions are classed chronic or autoimmune by vocabulary.",
        "* Risk cases (VIT-21 to VIT-25) are also run without the risk profile and extra history. Every rule's status and "
        "reasons must be identical to that control run.",
        "* The focus rule's status is read from `GET /patients/{id}/screening-preview`. The summary must agree with the "
        "preview rule by rule.",
        "* Timing: each read is repeated 5 times and the median is reported. Timings are in-process via TestClient (no "
        "network) on the development laptop. "
        f"The first preview per fresh database takes longer (median {statistics.median([r['timing_ms']['preview_all'][0] for r in results]):.1f} ms) "
        f"than repeated calls (median {statistics.median([t for r in results for t in r['timing_ms']['preview_all'][1:]]):.1f} ms). "
        "The maximum is a single repeated-call outlier, not a pattern.",
        "",
        "## Limitations",
        "",
        "* 25 cases, chosen by the dataset author. One case per behaviour in most dimensions, and only 3 in "
        "medication_exclusion and metformin. The agreement figures describe these cases only and are not a statistical "
        "estimate of accuracy.",
        "* The provisional labels were derived from the same code paths they test, so agreement shows consistency between "
        "code and labels, not clinical correctness.",
        "* Screening records were empty in every case, so history mappings were not exercised here (the unit tests cover "
        "them).",
        "* Clinical grounding of every rule is still pending: see `medical_team_review.xlsx`.",
    ]
    (RESULTS / "engine_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---------------------------------------------------------------- workbook
    wb = Workbook()
    head = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="2F6F8F")
    review_fill = PatternFill("solid", fgColor="FFF4CC")
    wrap = Alignment(wrap_text=True, vertical="top")

    ws = wb.active
    ws.title = "Instructions"
    for row in [
        ["VITALA screening engine: medical team review (25 synthetic cases)"],
        [""],
        ["What this is", "The engine's actual output for each synthetic case, with the rule, its eligibility text, its source and page."],
        ["What to do", "In 'Case review', fill the yellow columns: your own clinical label for the focus rule, whether the rule's eligibility is clinically grounded, and comments."],
        ["Labels", "candidate = the draft rule matched recorded data (NOT a recommendation); needs_information = undecided; not_applicable = recorded facts exclude it; not_triggered = no matching medication; archived_not_evaluated = rule retired with the medication scope change."],
        ["Independence", "Please label each case without looking at 'Actual engine status' first, so code concordance and clinician concordance stay separate metrics."],
        ["Data", "All patients are synthetic. No case is a real person."],
    ]:
        ws.append(row)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 120
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = wrap

    rules = {r["id"]: r for f in ("disease_rules.json", "medication_monitoring.json") for r in json.loads((DATA / f).read_text(encoding="utf-8"))}
    ws = wb.create_sheet("Case review")
    columns = ["Case", "Category", "Scenario", "Focus rule", "Rule action (ar)", "Eligibility text (ar)", "Schedule text (ar)",
               "Evidence (source: locator)", "Rule lifecycle", "Provisional label", "Actual engine status", "Engine reasons",
               "Deciding missing inputs", "Dataset explanation",
               "Clinician label", "Eligibility clinically grounded?", "Clinician comments", "Reviewer", "Review date"]
    ws.append(columns)
    for r in results:
        rule = rules[r["focus_rule_id"]]
        ws.append([r["case_id"], r["category"], r["scenario"], r["focus_rule_id"], rule["action_name_ar"], rule["eligibility_ar"],
                   rule["schedule"]["text_ar"], static[r["case_id"]][1], rule.get("lifecycle", "active"), r["provisional_expected_status"],
                   r["actual_status"], "; ".join(r["actual_reasons"]), "; ".join(r["deciding_missing_inputs"]), r["explanation_from_dataset"],
                   "", "", "", "", ""])
    label_dv = DataValidation(type="list", formula1='"candidate,needs_information,not_applicable,not_triggered,should_not_be_active,unsure"', allow_blank=True)
    grounded_dv = DataValidation(type="list", formula1='"yes,partly,no,unsure"', allow_blank=True)
    ws.add_data_validation(label_dv)
    ws.add_data_validation(grounded_dv)
    label_dv.add(f"O2:O{n + 1}")
    grounded_dv.add(f"P2:P{n + 1}")
    widths = [8, 13, 30, 9, 22, 30, 24, 34, 11, 16, 20, 22, 22, 45, 16, 16, 40, 14, 12]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    for cell in ws[1]:
        cell.font, cell.fill, cell.alignment = head, fill, wrap
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = wrap
        for cell in row[14:]:
            cell.fill = review_fill
    ws.freeze_panes = "E2"

    ws = wb.create_sheet("Checks")
    ws.append(["Case", "Kind", "Check", "Result"])
    for r in results:
        for kind, checks in (("gate", r["gate_checks"]), ("safety", r["safety_checks"]), ("traceability", r["traceability_checks"])):
            for name, ok in checks.items():
                ws.append([r["case_id"], kind, name, "PASS" if ok else "FAIL"])
    for cell in ws[1]:
        cell.font, cell.fill = head, fill
    ws.column_dimensions["C"].width = 48

    ws = wb.create_sheet("Metrics")
    for line in lines:
        if line.startswith("| ") and not line.startswith("|---"):
            cells = [c.strip().replace("**", "") for c in line.strip("|").split("|")]
            if cells[0] in ("Case",):
                break
            ws.append(cells)
    ws.column_dimensions["A"].width = 70
    ws.column_dimensions["B"].width = 70
    wb.save(RESULTS / "medical_team_review.xlsx")
    print("wrote", sorted(p.name for p in RESULTS.iterdir()))


if __name__ == "__main__":
    main()
