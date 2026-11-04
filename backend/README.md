# VITALA backend

Milestone one: patient profiles, medication use, and a medication catalogue.
Screening phase 1 adds a read-only screening preview built from the draft rules.

Later milestones will add reviewed recommendations, the Arabic chatbot, and
doctor and clinic features (see `docs/Vitala_App_Screens.pdf`). None of them exist yet.

## Limitations

- **No authentication.** Anyone who can reach the server can read and change
  every record. Use synthetic data only, never real patient information.
- **Local use only.** Keep the server on `127.0.0.1`. Do not use `--host 0.0.0.0`
  or expose it to a network.
- **No approved clinical logic.** The rule files in `data/` are drafts that no
  clinician has reviewed. The backend reads them only to build the screening
  preview described below. It does not generate recommendations or schedule
  anything. The date and status checks only catch data-entry mistakes.

## Setup

Run these in PowerShell from the `backend` folder. They call the environment's
Python directly, so you do not need to activate it or change the execution policy.

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Any Python from 3.12 upward is supported. Settings are optional: to change them,
copy `.env.example` to `.env`.

## Commands

Run from the `backend` folder:

```powershell
# Add the one synthetic patient. Running it again changes nothing.
.\.venv\Scripts\python.exe -m app.seed

# Start the server. Press Ctrl+C to stop it.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Run the tests. They use temporary databases, never vitala.db.
.\.venv\Scripts\python.exe -m pytest
```

- Health check: <http://127.0.0.1:8000/health>
- Interactive documentation: <http://127.0.0.1:8000/docs>

The server never seeds or overwrites records at startup. The database is always
`backend/vitala.db` unless `VITALA_DATABASE_PATH` says otherwise, wherever the
server was launched from. To start over, stop the server and delete that file.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | Server and database status |
| `POST /patients` | Create a profile |
| `GET /patients/{patient_id}` | Read a profile |
| `PATCH /patients/{patient_id}` | Update part of a profile |
| `GET /patients/{patient_id}/risk-profile` | Read risk factors (all unknown, `stored: false`, until saved) |
| `POST /patients/{patient_id}/risk-profile` | Create risk factors (409 if they exist) |
| `PATCH /patients/{patient_id}/risk-profile` | Update part of the risk factors |
| `GET /clinics` | List clinics (only the demo clinic, once seeded) |
| `GET /clinics/{clinic_id}` | Read one clinic |
| `GET /clinics/{clinic_id}/doctors` | List the clinic's doctors |
| `GET /clinics/{clinic_id}/patients` | List patients linked to the clinic |
| `GET /clinics/{clinic_id}/appointments` | List the clinic's appointments, oldest first |
| `GET /medications` | List the catalogue |
| `GET /medications/{medication_id}` | Read one catalogue entry |
| `POST /patients/{patient_id}/medications` | Add a medication use |
| `GET /patients/{patient_id}/medications` | List a patient's medication use |
| `PATCH /patients/{patient_id}/medications/{use_id}` | Update part of a medication use |
| `DELETE /patients/{patient_id}/medications/{use_id}` | Remove a medication use |
| `GET /screening-tests` | List the mapped screening tests and their rules |
| `GET /screening-history-mappings` | List which rule inputs recorded tests may provide, and their review status |
| `POST /patients/{patient_id}/screening-records` | Record a completed test |
| `GET /patients/{patient_id}/screening-records` | List a patient's screening history, newest first |
| `PATCH /patients/{patient_id}/screening-records/{record_id}` | Update part of a screening record |
| `DELETE /patients/{patient_id}/screening-records/{record_id}` | Remove a screening record |
| `GET /patients/{patient_id}/screening-preview` | Draft rules evaluated against the stored record |
| `GET /patients/{patient_id}/screening-summary` | Draft rules grouped by test, with recorded history |

## Rules the API applies

**Unknown is not negative.** Sex, diabetes status, diabetes type, and hypertension
status default to `unknown`. Only `not_diagnosed` states that a condition is
absent. A date that is `null` means not known.

**Partial updates.** In a `PATCH`, a field you leave out keeps its value and a date
sent as `null` is cleared. Status fields and dose text cannot be `null`; send
`unknown` for a status instead.

**Validation (status 422).**

- Dates use `YYYY-MM-DD` and cannot be in the future.
- Diagnosis and medication dates cannot be before the date of birth.
- A last dose change cannot be before the start date.
- A diagnosis date or a diabetes type requires the status `diagnosed`. To move a
  status away from `diagnosed`, clear those fields in the same request.
- `medication_id` must exactly match a catalogue id.
- Misspelled or unexpected fields are rejected.

**Other responses.** A missing patient or medication use returns 404. Adding a
medication the patient already has returns 409: update that record instead. To
correct the wrong medication, remove the record and add the right one.

## Screening preview

`GET /patients/{patient_id}/screening-preview` evaluates every draft rule against
the patient's profile and recorded medications. It writes nothing. Every response
carries `clinically_approved: false` and `auto_schedule_enabled: false`. Each rule
appears with its sources, conflicts, review flags, and `review_status`. Each rule
gets one of these statuses:

| Status | Meaning |
|---|---|
| `candidate` | The recorded data meets every eligibility condition the engine can check. A candidate for clinician review, not a recommendation. |
| `needs_information` | Eligibility depends on something unknown. The deciding fields have `affects_eligibility: true`. |
| `not_applicable` | Recorded data excludes this rule, for example `diabetes_not_diagnosed`. The test may still be needed for other reasons. |
| `not_triggered` | Medication rule with none of its medications recorded. The list may be incomplete, so this is not a negative finding. |

`missing_inputs` lists every input the rule needs that is not available. `unknown`
means VITALA records the field but it is empty. `not_collected` means VITALA does
not record that field yet. No value is ever assumed. The response gives the
schedule as source text only, never as a date or interval to book.

The rules describe eligibility in Arabic prose. `app/screening.py` (`CRITERIA`)
turns it into checks, using only the fields VITALA stores. That reading is as
unreviewed as the rules. The app refuses to start if a rule has no criteria, if a
rule is anything other than `draft_not_clinician_reviewed` with scheduling off,
or if any source, conflict, knowledge, or medication reference does not resolve.

## Demo clinic

`python -m app.seed` also creates one synthetic demo clinic (`is_demo: true`): three
doctors, five new synthetic patients linked to it, and seven appointments with
fixed dates. Names say they are synthetic, and the patients hold basic profile
facts only. Running the command again changes nothing, and it never edits or links
patients it did not create. The server never seeds at startup, so the clinic
endpoints return an empty list until the command has run.

Every clinic-side row carries `clinic_id`, ready for more clinics later. A clinic
sees a patient only through a `clinicpatient` link, so unlinked patients stay
private. Appointments point at that link, so they always belong to a clinic the
patient is registered with. `scheduled_at` is stored in UTC and shown in the
clinic's `time_zone`. `booking_source` is simulated in the demo and is labelled so.
The clinic endpoints are read-only in this phase.

There is no authentication: choosing the clinic entry grants no access and
protects nothing. Keep the server local and the data synthetic.

## Risk factors

`patientriskprofile` holds one row per patient: smoking (`current`, `former`,
`never`, `unknown`), height in cm (50–250), weight in kg (2–350), physical activity
in minutes per week (0–10080), and `yes`/`no`/`unknown` for raised lipids,
pregnancy, and family history of diabetes, heart disease, breast cancer, and
colorectal cancer. Every value defaults to unknown or null, and neither means "no".
Numbers must be real JSON numbers. `bmi` is calculated in each response and never
stored. Pregnancy cannot be `yes` for a patient recorded as male, in either order
of saving. Kidney disease is not collected here: it is a clinical assessment.

**The screening engine does not read risk factors.** None of the draft rules use
smoking, BMI, activity, or family history, and the HTN03 pregnancy criterion stays
`not_collected` until a clinician approves using it. Tests check that the preview
and summary are identical with and without a risk profile.

## Screening history

A screening record is one completed test: `test_id` (an id from
`GET /screening-tests`), `test_name` as written on the report, `completed_on`,
an optional `result` and `unit`, a `source` (`patient_reported`, `lab_report`,
`clinician_entered`, or `device`), and optional `notes`. A patient may have any
number of records for the same test. Results are stored exactly as entered and
are never interpreted. Completion dates cannot be in the future or before the
date of birth, and a unit requires a result. To record a different test, remove
the record and add the right one.

## Screening summary

`GET /patients/{patient_id}/screening-summary` groups the preview's rule results
by test and lists the patient's recorded tests next to them. It writes nothing
and calculates no due dates. The rule results are exactly those of the preview.
Recorded history affects them only through approved history mappings (below),
and none is approved yet.

For each test the summary separates:

- `recorded_tests`: completed tests on record, newest first.
- `history_inputs`: each rule input the recorded tests may provide, with the
  mapping's status, whether it is `applied`, the record count, and the latest
  completion date. A pending mapping is shown here but never applied.
- `ambiguous_history_fields`: inputs these records might relate to but are not
  mapped to, with the reason.
- `candidate_rule_ids`, `needs_information_rule_ids`, `not_applicable_rule_ids`,
  `not_triggered_rule_ids`: each rule under its own status, never combined.
- `missing_inputs`: the preview's missing inputs, each listing the rules that need it.
- `review_reasons`: why the test needs clinical review, given only when the test
  concerns the patient: `draft_rules`, `draft_test_grouping`, `source_conflict`,
  `mixed_rule_statuses` (candidate and needs-information rules together),
  `possible_overlap`, `history_not_used_by_rules`, `history_mapping_pending_review`,
  `ambiguous_history_mapping`, and `multiple_records_same_date`.
- `rules`: every rule in full, with its sources and review status.

Rules are grouped only by the explicit table in `app/screening_tests.py`, never
by similar names. That table is an unreviewed mapping (`mapping_status`). Tests
that only partly overlap, such as eGFR and creatinine with potassium, stay
separate and are listed in `possible_overlap_test_ids`. The app refuses to start
unless every rule belongs to exactly one test. Records whose test is no longer
mapped appear in `unmapped_records` rather than being dropped.

## History mappings

`app/history_mappings.py` lists, one versioned entry at a time, which rule input
a recorded test may provide. A mapping states a direct fact only: when a test of
that kind was last completed (`completion_date`), or that one is on record
(`test_on_record`). Results are never read, and no record ever means "not done".

- Every mapping starts as `pending_review`. A pending mapping never changes rule
  evaluation. Its data appears only in the summary's `history_inputs`.
- An approved mapping needs a reviewer and a review date. It then supplies the
  fact to rules in its own test group only. With no record, the input becomes
  `unknown` instead of `not_collected`.
- `changes_eligibility` marks a mapping that can change a rule's status. Today
  that is only `HM05`: DM07 applies once a previous eye exam is on record.
- `CLINICAL_INTERPRETATIONS`, such as `hba1c_at_individual_target`, can never be
  mapped. A clinician must enter them.
- `AMBIGUOUS_HISTORY_FIELDS` lists connections left unmapped on purpose, such as
  an eGFR record and a rule asking for the last creatinine date.

The app refuses to start if a mapping targets an interpretation, an unknown test,
or a field no rule in its group uses. It also refuses one whose value would decide
eligibility, one with inconsistent review details, or one that overlaps an
ambiguous entry.

## Data

`data/` holds byte-for-byte copies of the collected research dataset (version
0.1.0, status `research_draft_not_clinically_validated`). Do not edit these files
by hand: source IDs, links, review flags, and draft statuses must stay as collected.
`.gitattributes` stops Git from changing their line endings.

The backend reads `medications.json`, the two rule files, `sources.json`,
`conflicts.json`, and the IDs in `explanation_knowledge.json`. It never writes them.
The medication list is a practical starting selection, not a ranking of the most
dispensed medications in Saudi Arabia. A medication's absence from it does not
mean the medication needs no monitoring.
