# VITALA screening engine: 25-case synthetic validation

Run: 2026-11-14T02:26:07.354581+00:00 · branch `integration/rag-risk-profile-meds-scope` · Python 3.15.2 · total runtime 11.8 s · temporary SQLite database per case.

> **Not clinical validation.** The labels are the dataset's *provisional* expectations, inferred from the pre-integration code. `clinician_gold_label` is blank for all 25 cases, so clinician concordance cannot be computed. `candidate` means a draft rule matched recorded data. It is not a recommendation.

## Headline metrics

| Metric | Result |
|---|---|
| Overall pass (post-update gate + every safety safeguard) | **25/25 (100.0%)** |
| Post-update gate pass | 25/25 (100.0%) (61/61 individual gate checks) |
| Safety safeguards held in every case | 25/25 (100.0%) (275/275 checks) |
| Agreement with the provisional label, all cases | 23/25 (92.0%), Cohen's κ = 0.888 |
| Agreement with the provisional label, excluding the 2 intentional scope changes | 23/23 (100.0%), κ = 1.000 |
| Runtime traceability (evaluated focus rule → source + locator + URL + review status) | 24/24 (100.0%) |
| Static traceability (focus rule id → rule file → registered source + locator) | 25/25 (100.0%) |
| Clinician concordance | not computable: 0/25 gold labels filled |
| Screening preview latency | median 7.1 ms, p95 37.0 ms, max 118.1 ms (125 calls) |
| Clinician summary latency | median 11.8 ms, max 13.9 ms |
| Loading one case through the API | median 45.7 ms, max 96.1 ms |

The two label disagreements are **VIT-19** and **VIT-20**. Their provisional labels describe the legacy engine (losartan → MED05 candidate, atorvastatin → MED07 candidate). The dataset requires them to stop being active (`exclude_out_of_scope_medication_rules`), and they did: MED05 is `not_triggered` for losartan, and MED07 is archived and not evaluated. Both prescriptions remain stored unchanged.

## Results by dimension

| Dimension | Cases | Pass | Notes |
|---|---|---|---|
| ace_inhibitors | 4 | 4/4 (100.0%) | MED03/04/05 trigger on enalapril/lisinopril; unknown diabetes → needs_information |
| allergies | 1 | 1/1 (100.0%) | stored, shown in the clinician summary, no effect on screening |
| diabetes | 6 | 6/6 (100.0%) | DM01/DM03: type 1 duration, unknown type, not diagnosed |
| hypertension | 5 | 5/5 (100.0%) | HTN01/03/04: unknown status stays undecided; recorded-but-unapproved pregnancy never applied |
| medication_exclusion | 2 | 2/2 (100.0%) | archived drugs refused by the API, historical record intact, no active rule |
| metformin | 3 | 3/3 (100.0%) | MED01/MED02 trigger; no metformin → not_triggered |
| missing_data | 8 | 8/8 (100.0%) | unknown values never produce not_applicable |
| risk_factors | 5 | 5/5 (100.0%) | statuses identical to a control run without the data; stored and shown; nothing actionable |

## Per-case results

| Case | Scenario | Focus | Provisional | Actual | Gate | Safety | Overall | Source |
|---|---|---|---|---|---|---|---|---|
| VIT-01 | Diagnosed type 2 diabetes | DM03 | candidate | candidate | ✔ existing_logic | ✔ | PASS | S01: فقرة ACR |
| VIT-02 | Type 1 diabetes diagnosed under five years ago | DM03 | not_applicable | not_applicable | ✔ existing_logic | ✔ | PASS | S01: فقرة ACR |
| VIT-03 | Type 1 diabetes diagnosed over five years ago | DM03 | candidate | candidate | ✔ existing_logic | ✔ | PASS | S01: فقرة ACR |
| VIT-04 | Diabetes diagnosed, type missing | DM03 | needs_information | needs_information | ✔ existing_logic | ✔ | PASS | S01: فقرة ACR |
| VIT-05 | Diabetes recorded as not diagnosed | DM03 | not_applicable | not_applicable | ✔ existing_logic | ✔ | PASS | S01: فقرة ACR |
| VIT-06 | A1c target interpretation missing | DM01 | needs_information | needs_information | ✔ existing_logic | ✔ | PASS | S01: فقرة A1C |
| VIT-07 | Hypertension diagnosed; pregnancy details unknown | HTN03 | needs_information | needs_information | ✔ existing_logic | ✔ | PASS | S04: PDF pp. 16, 35–36 |
| VIT-08 | Hypertension explicitly not diagnosed | HTN03 | not_applicable | not_applicable | ✔ existing_logic | ✔ | PASS | S04: PDF pp. 16, 35–36 |
| VIT-09 | Hypertension diagnosis status unknown | HTN03 | needs_information | needs_information | ✔ existing_logic | ✔ | PASS | S04: PDF pp. 16, 35–36 |
| VIT-10 | Hypertension with BP control not recorded | HTN01 | needs_information | needs_information | ✔ existing_logic | ✔ | PASS | S04: PDF p. 52 |
| VIT-11 | Hypertension kidney assessment depends on clinician | HTN04 | needs_information | needs_information | ✔ existing_logic | ✔ | PASS | S04: PDF pp. 35–36 |
| VIT-12 | Metformin: vitamin B12 monitoring draft | MED01 | candidate | candidate | ✔ existing_logic | ✔ | PASS | S02: PDF p. 53 |
| VIT-13 | Metformin: kidney monitoring draft | MED02 | candidate | candidate | ✔ existing_logic | ✔ | PASS | S02: PDF p. 84 |
| VIT-14 | Lisinopril with diagnosed diabetes | MED03 | candidate | candidate | ✔ existing_logic | ✔ | PASS | S02: PDF p. 83 |
| VIT-15 | Enalapril with diagnosed diabetes | MED04 | candidate | candidate | ✔ existing_logic | ✔ | PASS | S03: PDF p. 26, hypertension item l |
| VIT-16 | Lisinopril without diagnosed diabetes | MED05 | candidate | candidate | ✔ existing_logic | ✔ | PASS | S04: PDF pp. 55–56 |
| VIT-17 | ACE inhibitor with diabetes status unknown | MED03 | needs_information | needs_information | ✔ existing_logic | ✔ | PASS | S02: PDF p. 83 |
| VIT-18 | No metformin medication recorded | MED01 | not_triggered | not_triggered | ✔ existing_logic | ✔ | PASS | S02: PDF p. 53 |
| VIT-19 | Losartan is out of the new ACE-inhibitor demo scope | MED05 | candidate | not_triggered | ✔ exclude_out_of_scope_medication_rules | ✔ | PASS | S04: PDF pp. 55–56 |
| VIT-20 | Atorvastatin out of new medication demo scope | MED07 | candidate | archived_not_evaluated | ✔ exclude_out_of_scope_medication_rules | ✔ | PASS | S03: PDF p. 26, dyslipidemia item b (lifecycle: archived) |
| VIT-21 | Current smoking without diagnosed diabetes | DM03 | not_applicable | not_applicable | ✔ no_unapproved_risk_recommendation | ✔ | PASS | S01: فقرة ACR |
| VIT-22 | Family cancer history with two affected relatives | DM03 | not_applicable | not_applicable | ✔ store_display_no_unapproved_cancer_rule | ✔ | PASS | S01: فقرة ACR |
| VIT-23 | Patient-reported genetic mutation without verification | DM03 | not_applicable | not_applicable | ✔ store_display_no_unapproved_genetic_rule | ✔ | PASS | S01: فقرة ACR |
| VIT-24 | High BMI, inactivity, family diabetes and autoimmune history | DM03 | not_applicable | not_applicable | ✔ record_risk_factors_no_new_unapproved_rules | ✔ | PASS | S01: فقرة ACR |
| VIT-25 | Allergies present, risk factors missing | DM03 | not_applicable | not_applicable | ✔ allergy_display_only_and_preserve_unknown | ✔ | PASS | S01: فقرة ACR |

## Safety safeguards checked in every case

| Safeguard | Held |
|---|---|
| auto_schedule_disabled | 25/25 (100.0%) |
| not_clinically_approved | 25/25 (100.0%) |
| all_rules_draft | 25/25 (100.0%) |
| no_due_dates | 25/25 (100.0%) |
| no_archived_rule_evaluated | 25/25 (100.0%) |
| no_proposal_evaluated | 25/25 (100.0%) |
| unknown_never_negative | 25/25 (100.0%) |
| no_actionable_risk_factor | 25/25 (100.0%) |
| preview_matches_summary | 25/25 (100.0%) |
| clinician_summary_ok | 25/25 (100.0%) |
| load_without_errors | 25/25 (100.0%) |

## Can the harness fail? (mutation check)

Each defect was injected in memory into the engine and the 25 cases were rerun. The rule files were not changed.

| Injected defect | Detected | Cases that failed |
|---|---|---|
| reactivate_archived_medication_rules | yes | VIT-19, VIT-20 |
| assume_diabetes_type_when_unknown | yes | VIT-04 |
| approve_unreviewed_risk_mapping | yes | VIT-01, VIT-02, VIT-03, VIT-04, VIT-05, VIT-06, VIT-07, VIT-08, VIT-09, VIT-10, VIT-11, VIT-12, VIT-13, VIT-14, VIT-15, VIT-16, VIT-17, VIT-18, VIT-19, VIT-20, VIT-21, VIT-22, VIT-23, VIT-24, VIT-25 |
| (unmutated engine rerun) | all pass: True | |

Adding `unknown` to DM03's allowed diabetes types did *not* change the engine's output: the engine tests for an unknown type before it checks the type list. That mutation was replaced with one that rewrites an unknown type as type 2, which VIT-04 catches. Only one case (VIT-04) guards that defect, so coverage of missing-data paths is thin.

## Method

* Each case runs against a new temporary database through the public API: patient, risk profile, medications, allergies, family relatives and conditions, and genetic findings. Two steps have no API and use a test fixture: linking the patient to a clinic appointment (to read the clinician summary), and storing a historical prescription of an archived medicine after the API refused it (VIT-19, VIT-20).
* The dataset's `additional_medical_history` shapes were mapped onto the new endpoints: `relative_key` becomes one relative record, `patient_reported_unverified` becomes `verification: patient_reported`, `diagnosed_age` becomes `age_at_diagnosis`, and conditions are classed chronic or autoimmune by vocabulary.
* Risk cases (VIT-21 to VIT-25) are also run without the risk profile and extra history. Every rule's status and reasons must be identical to that control run.
* The focus rule's status is read from `GET /patients/{id}/screening-preview`. The summary must agree with the preview rule by rule.
* Timing: each read is repeated 5 times and the median is reported. Timings are in-process via TestClient (no network) on the development laptop. The first preview per fresh database takes longer (median 34.6 ms) than repeated calls (median 6.9 ms). The maximum is a single repeated-call outlier, not a pattern.

## Limitations

* 25 cases, chosen by the dataset author. One case per behaviour in most dimensions, and only 3 in medication_exclusion and metformin. The agreement figures describe these cases only and are not a statistical estimate of accuracy.
* The provisional labels were derived from the same code paths they test, so agreement shows consistency between code and labels, not clinical correctness.
* Screening records were empty in every case, so history mappings were not exercised here (the unit tests cover them).
* Clinical grounding of every rule is still pending: see `medical_team_review.xlsx`.
