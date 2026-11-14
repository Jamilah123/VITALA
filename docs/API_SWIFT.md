# VITALA backend API for the iOS app

Every example below is a real response produced by the backend (seeded synthetic data). The full, always-current
schema is at `http://127.0.0.1:8000/docs` (OpenAPI JSON: `/openapi.json`); you can generate Codable models from it.

## Ground rules

| Topic | Rule |
|---|---|
| Base URL | `http://127.0.0.1:8000` on the machine running the backend. The backend binds to localhost only. |
| Authentication | **None yet.** There is no login, token or user. Every endpoint is open to whoever reaches the server. Use synthetic data only. Treat the patient and clinic ids in paths as identifiers, not as access control. |
| Format | JSON, UTF-8. Dates are `YYYY-MM-DD` strings. Times are ISO 8601 with an offset (`2026-11-25T10:00:00+03:00`); responses return UTC (`...Z`). |
| Enums | Lower-case strings. Decode them as `String`-backed enums **with an unknown fallback**, because new values may be added (this release added `recorded_pending_review`). |
| Unknown vs no | `"unknown"` means not recorded. It never means "no". Only `"no"` / `"not_diagnosed"` / `"absent"` state a negative. Show unknown as "not recorded", never as a negative finding. |
| Nulls | A `null` field means not available. Never substitute a default value in the UI. |
| New fields | Responses can gain fields. Make Codable structs tolerate extra keys (Swift's default) and mark the new ones optional. |

### Errors

| Status | Body | Meaning |
|---|---|---|
| 404 | `{"detail": "Patient 9 not found"}` | Missing id, or an id that belongs to another patient or clinic |
| 409 | `{"detail": "..."}` or `{"detail": {"code": "...", "message": "..."}}` | Duplicate (same allergen, same national ID, same medication) |
| 422 | `{"detail": [{"loc": ["body", "field"], "msg": "...", "type": "..."}]}` | Validation. `loc.last` is the field to highlight. Insurance errors never echo the submitted value. |
| 403 | `{"detail": {"code": "patient_context_disabled", "message": "..."}}` | The assistant may use only synthetic demo patients' data |
| 501 | `{"detail": {"code": "virtual_care_not_implemented", ...}}` | Video visits do not exist yet |
| 503 | `{"detail": {"code": "chat_unavailable" \| "encryption_not_configured", "message": "..."}}` | The assistant is not running, or the server has no encryption key |

`detail` is a string, an object, or an array depending on the error, so decode it as a JSON enum.

---

## 1. Medical history and risk factors

### Summary flags (existing endpoint, new fields)

`PATCH /patients/{id}/risk-profile` (create first with `POST`; `GET` works before anything is saved)

```json
{"smoking_status": "former", "information_source": "patient_reported",
 "known_allergies": "yes", "family_cancer_history": "yes",
 "family_chronic_or_autoimmune_history": "unknown", "known_genetic_findings": "no"}
```

* `smoking_status`: `current | former | never | unknown`. The other flags are `yes | no | unknown`.
* `information_source` applies to the whole profile: `patient_reported | clinically_confirmed | unknown`.
* A flag cannot be `"no"` while matching records exist, and records cannot be added while it is `"no"`. Both cases
  return 422 on that flag. Set it to `unknown` or `yes` first.

### Allergies

| Method | Path |
|---|---|
| `GET` / `POST` | `/patients/{id}/allergies` |
| `PATCH` / `DELETE` | `/patients/{id}/allergies/{allergy_id}` |

```json
POST {"allergen": "Penicillin", "category": "drug", "reaction": "Skin rash",
      "severity": "moderate", "verification": "patient_reported"}
```
Only `allergen` is required. `category`: `drug | food | environmental | other | unknown`. `severity`: `mild | moderate |
severe | life_threatening | unknown`. Repeating the same allergen in any letter case returns 409.

### Family history (cancer, chronic and autoimmune)

Each affected relative is one record, so two sisters are two records and a relative with two conditions is counted
once. The allowed codes come from `GET /medical-history/vocabulary`.

| Method | Path |
|---|---|
| `GET` | `/patients/{id}/family-history` |
| `POST` | `/patients/{id}/family-history/relatives` (optionally with `conditions`) |
| `PATCH` / `DELETE` | `/patients/{id}/family-history/relatives/{relative_id}` (deleting also removes the relative's conditions) |
| `POST` | `/patients/{id}/family-history/relatives/{relative_id}/conditions` |
| `PATCH` / `DELETE` | `/patients/{id}/family-history/conditions/{condition_id}` |

```json
POST {"relationship": "father",
      "conditions": [{"category": "chronic", "condition": "hypertension", "verification": "patient_reported"}]}

201 {"id": 3, "patient_id": 7, "relationship": "father", "degree": "first", "label": null,
     "conditions": [{"id": 4, "relative_id": 3, "category": "chronic", "condition": "hypertension",
                     "condition_other": null, "age_at_diagnosis": null, "verification": "patient_reported"}]}
```
* `category`: `cancer | chronic | autoimmune`. `condition: "other"` requires `condition_other` text.
* `label` tells relatives with the same relationship apart (for example "older sister").
* `age_at_diagnosis` is optional (0–120).

### Genetic findings

`GET` / `POST /patients/{id}/genetic-findings`, `PATCH` / `DELETE /patients/{id}/genetic-findings/{finding_id}`

```json
POST {"name": "BRCA1 pathogenic variant", "gene": "BRCA1", "verification": "patient_reported",
      "test_source": "Lab report", "test_date": "2024-03-01"}
```
`verification` defaults to `unknown`. Show anything that isn't `clinically_confirmed` as unconfirmed. VITALA infers
nothing from a finding.

### Everything in one call

`GET /patients/{id}/medical-history` (shortened)

```json
{"patient_id": 7,
 "risk_profile": {"smoking_status": "former", "bmi": 30.5, "known_allergies": "yes", "known_genetic_findings": "unknown", "...": "..."},
 "allergies": [{"id": 1, "allergen": "Penicillin", "category": "drug", "reaction": "Skin rash", "severity": "moderate", "verification": "patient_reported", "notes": null}],
 "family_relatives": [{"id": 1, "relationship": "mother", "degree": "first", "conditions": [{"category": "cancer", "condition": "breast", "age_at_diagnosis": 62, "verification": "patient_reported"}]}],
 "family_counts": {"relatives_with_cancer": 2, "first_degree_relatives_with_cancer": 2, "relatives_with_chronic_or_autoimmune": 1},
 "genetic_findings": [],
 "risk_factors": [{"field": "smoking_status", "state": "present", "value": "former", "source": "patient_reported",
                   "rule_ids": [], "actionable": false, "actionable_rule_ids": [], "detail": {}}],
 "consistency_notes": [],
 "screening_uses_risk_factors": false,
 "notice": "Recorded for the clinician and the patient. No risk factor ... changes a screening status until a clinician approves the mapping."}
```
`risk_factors[].state` is `present | absent | unknown | value`. `actionable` is false for every factor today.

## 2. Screening plan (read-only, draft)

`GET /patients/{id}/screening-summary` (grouped by test) or `/screening-preview` (flat list of rules).

* `clinically_approved` and `auto_schedule_enabled` are always `false`. Show the result as a **draft for clinician
  review, not a recommendation**. There are no due dates; don't compute any.
* Rule `status`: `candidate | needs_information | not_applicable | not_triggered`.
* `missing_inputs[].reason`: `unknown` (VITALA records it, it is empty) · `not_collected` (VITALA doesn't record it) ·
  `recorded_pending_review` (stored, but the rules may not use it until approved).
* New: `risk_factors` (as above), `out_of_scope_medications` (recorded archived medicines), and per test
  `archived_rule_ids`.
* Medication scope: `GET /medication-scope`. The catalogue (`GET /medications`) returns every entry with
  `status: "active" | "archived"`. Offer only active ones when adding a medicine; adding an archived one returns 422.

## 3. Clinician summary

`GET /clinics/{clinic_id}/appointments/{appointment_id}/summary`. The top-level keys are
`clinic, visit, risk_profile, medications, screening, medical_history, insurance, smartwatch_data_available,
clinically_validated`.
`medical_history` is the object from section 1. `insurance` holds `coverage_status`, `insurer_name`,
`insurance_class` and `eligibility_verified: false`, with no identifiers. Each `medications[]` entry carries
`catalogue_status`.

## 4. Chat with VITALA

`GET /chat/status`: `{"available": true, "llm_provider": "azure_openai", "pipeline_version": "0.2.0", "patient_context_policy": "synthetic_demo_patients_only"}`.
Call it before showing the chat. If `available` is false, show the chat as unavailable.

`POST /chat`

```json
{"question": "هل يحتاج الميتفورمين متابعة لوظائف الكلى؟"}
{"question": "What is in my screening plan?", "patient_id": 7}
```
* Without `patient_id`: a general question; no personal data is sent.
* With `patient_id`: allowed **only for synthetic demo patients** created by the seed command. Any other patient
  returns 403 `patient_context_disabled`. Never send real patients.
* Arabic and English both work, and the answer comes back in the question's language.

```json
200 {"request_id": "...", "status": "answered", "language": "en",
     "answer": "General information [E1].",
     "display_text": "General information.",
     "notices": ["Discuss with your clinician."],
     "citations": [{"evidence_id": "E1", "source_id": "STATPEARLS-METFORMIN-2023", "collection": "medication",
                    "title": "StatPearls: Metformin", "citation": "StatPearls: Metformin, p. 4", "url": "", "pdf_page": 4}],
     "safety_flags": [], "route": "medical", "disclaimer": "General information, not a diagnosis.",
     "llm_provider": "azure_openai",
     "patient_context": {"used": false, "synthetic": false, "patient_id": null, "fields_sent": []},
     "is_medical_advice": false}
```
* Show `display_text` (no citation markers), then `notices`, then the sources. `answer` keeps `[E#]`/`[P#]` markers
  for logs.
* Handle each `status`: `emergency_escalation` (show prominently; it includes the Saudi ambulance number 997),
  `declined_personal_advice`, `declined_out_of_scope`, `insufficient_evidence`, `patient_data_unavailable`,
  `grounding_fallback` (quotes only), and `error`.
* A 503 `chat_unavailable` means the assistant isn't running. Show a retry state.
* Allow up to 60–90 s for a reply.

## 5. Analyze with VITALA

`POST /patients/{id}/screening-records/{record_id}/analysis` with `{"language": "ar"}` or `"en"`.

```json
200 {"result": {"record_id": 1, "test_id": "hba1c", "test_name": "HbA1c", "result": "7.4", "unit": "%",
                "completed_on": "2026-08-10", "reference_range": "4.0-5.6 % (synthetic lab range)",
                "source": "lab_report", "missing_fields": []},
     "explanation": { "...same shape as a chat reply..." },
     "limitations": ["VITALA does not interpret your personal result or diagnose. Please discuss it with your clinician.",
                     "The explanation uses general reference sources that have not been clinically reviewed for VITALA."],
     "interpreted_by_vitala": false}
```
* Only this one result (plus age, sex, conditions, medicines and recorded risk factors) is sent. No other results,
  no insurance, no names.
* `missing_fields` lists `unit` and/or `reference_range` when they weren't recorded. Show "not recorded"; never fill
  one in. A `limitations` line explains it.
* 403 for non-synthetic patients · 404 if the record isn't this patient's · 422 if the record has no result value ·
  503 if the assistant is down.
* Records accept an optional `reference_range` (text exactly as printed by the lab) on `POST` / `PATCH`
  `/patients/{id}/screening-records`.

## 6. Appointment type

The clinic endpoints accept `appointment_type: "in_person" | "virtual"` (default `in_person`) on `POST` and `PATCH`
`/clinics/{clinic_id}/appointments[/{appointment_id}]`. Every appointment returns:

```json
{"id": 8, "scheduled_at": "2026-11-25T07:00:00Z", "status": "scheduled", "booking_source": "vitala",
 "visit_reason_ar": "متابعة السكري عن بعد", "appointment_type": "virtual", "virtual_session_status": "not_available", "...": "..."}
```
**Video is not implemented.** `GET /clinics/{c}/appointments/{a}/virtual-session` returns 501 for virtual appointments
and 409 for in-person ones. Don't show a "Join call" button; show "the clinic will contact you" instead. Appointments
created before this release read as `in_person`.

## 7. Insurance (sensitive)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/patients/{id}/insurance` | Masked values only |
| `PUT` | `/patients/{id}/insurance` | Replaces everything; omitted fields are cleared |
| `DELETE` | `/patients/{id}/insurance` | |

```json
PUT {"coverage_status": "insured", "national_id": "1000000008", "insurer_name": "Synthetic Insurer",
     "member_number": "SYN-123456", "insurance_class": "B"}

200 {"patient_id": 7, "stored": true, "coverage_status": "insured", "insurer_name": "Synthetic Insurer",
     "insurance_class": "B", "national_id_masked": "******0008", "member_number_masked": "****3456",
     "updated_at": "2026-11-14T02:03:05.105636Z",
     "eligibility_verified": false, "insurer_integration_available": false, "online_payment_available": false}
```
* `coverage_status`: `insured | uninsured | unknown`. The detail fields are allowed only when `insured` (422
  otherwise).
* `national_id`: 10 digits starting with 1 or 2 (format check only). `member_number`: 3–40 letters, digits or `-`.
* Full values are **never** returned. Don't cache them on the device after sending.
* 503 `encryption_not_configured` means the server has no encryption key. Insurer name and class still save.
* 409 `national_id_in_use` means the ID is already on another patient.
* Eligibility checks, insurer integration and online payment **do not exist**. Don't present them as working.

## Running the backend for the app

See the root `README.md` → "Usage". The iOS Simulator on the same Mac reaches `http://127.0.0.1:8000`.
A physical device or another machine **cannot** reach it, because the server binds to localhost on purpose (no
authentication). For a device demo, run the backend on the Mac that runs the simulator. Exposing it on a network is
a separate decision for the team: synthetic data only, and only for the duration of a demo.
