# VITALA backend

Milestone one: patient profiles, medication use, and a medication catalogue.

Later milestones will add recommendations, the Arabic chatbot, and the frontend
(see `docs/Vitala_App_Screens.pdf`). None of them exist yet.

## Limitations

- **No authentication.** Anyone who can reach the server can read and change
  every record. Use synthetic data only, never real patient information.
- **Local use only.** Keep the server on `127.0.0.1`. Do not use `--host 0.0.0.0`
  or expose it to a network.
- **No clinical logic.** The rule files in `data/` are drafts that no clinician
  has reviewed. The backend does not read them or generate recommendations.
  The date and status checks only catch data-entry mistakes.

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
| `GET /medications` | List the catalogue |
| `GET /medications/{medication_id}` | Read one catalogue entry |
| `POST /patients/{patient_id}/medications` | Add a medication use |
| `GET /patients/{patient_id}/medications` | List a patient's medication use |
| `PATCH /patients/{patient_id}/medications/{use_id}` | Update part of a medication use |
| `DELETE /patients/{patient_id}/medications/{use_id}` | Remove a medication use |

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

## Data

`data/` holds byte-for-byte copies of the collected research dataset (version
0.1.0, status `research_draft_not_clinically_validated`). Do not edit these files
by hand: source IDs, links, review flags, and draft statuses must stay as collected.
`.gitattributes` stops Git from changing their line endings.

Only `medications.json` is loaded at this stage. The list is a practical starting
selection, not a ranking of the most dispensed medications in Saudi Arabia. A
medication's absence from it does not mean the medication needs no monitoring.
