# VITALA

VITALA is a preventive-health prototype for patients and clinics in Saudi Arabia. It stores patient
health profiles, previews draft screening rules, manages clinic appointments, and includes a bilingual
(Arabic and English) chatbot that answers from cited sources.

> Research prototype. The screening rules and chatbot sources have not been reviewed by a clinician,
> there is no authentication, and all patient data is synthetic. Do not use it with real patient data.

## Features

- Patient profiles: conditions, medications, allergies, family and genetic history, risk factors
- Read-only screening preview built from draft rules, with missing information shown as unknown
- Demo clinic workspace: appointments (in person or virtual) and a pre-appointment summary
- Encrypted storage for national IDs and insurance member numbers
- RAG chatbot for preventive health, metformin and ACE inhibitors, and app usage, with a
  grounding check on every answer
- Arabic, right-to-left web app

## Tech stack

- **Backend:** Python 3.12+, FastAPI, SQLModel, SQLite
- **Frontend:** React, TypeScript, Vite (Node.js 22+)
- **Chatbot:** Python 3.12, multilingual-e5 embeddings, FAISS and BM25 hybrid search, FastAPI and Gradio,
  with Azure OpenAI, Anthropic or an OpenAI-compatible model (optional)

## Installation

Commands are for PowerShell on Windows, run from the repository root.

```powershell
# Backend
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.seed          # adds synthetic demo data

# Chatbot (optional)
cd ..\rag
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Frontend
cd ..\frontend
npm install
```

The chatbot's search indexes are not in the repository because most source documents may not be
redistributed. Rebuild them with `python -m vitala_rag build` once the documents are in `rag/data/raw/`.

## Usage

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1   # chatbot :8001 (new window), backend :8000
cd frontend; npm run dev                                       # web app at http://127.0.0.1:5173
```

API documentation is served at `http://127.0.0.1:8000/docs`. The backend runs without the chatbot.
Chat requests return 503 until it is started. The iOS client API is described in
[docs/API_SWIFT.md](docs/API_SWIFT.md).

Tests: `python -m pytest` in `backend` and in `rag` (with `PYTHONPATH=src`), and `npm test` in `frontend`.

## Configuration

Copy `backend/.env.example` to `backend/.env` and `rag/.env.example` to `rag/.env`. Never commit `.env` files.

| Variable | Purpose |
|---|---|
| `VITALA_DATABASE_PATH` | SQLite file (default `backend/vitala.db`) |
| `VITALA_CORS_ORIGINS` | Allowed frontend origins, as a JSON list |
| `VITALA_RAG_URL` | Chatbot address (default `http://127.0.0.1:8001`) |
| `VITALA_FIELD_ENCRYPTION_KEY` | Fernet key for national ID and insurance numbers; those fields cannot be saved without it |
| `VITALA_BACKUP_DIR` | Where the database is copied before a migration |
| `VITALA_LLM_PROVIDER` | `azure_openai`, `anthropic`, `openai_compatible` or `extractive` (no LLM, quotes only) |
| `AZURE_OPENAI_*`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Credentials for the chosen provider |
| `VITALA_DEBUG` | `1` shows developer diagnostics in the chatbot. Never enable it for patients |

## Project structure

```text
backend/            FastAPI service: models, migrations, screening engine, routers, tests
  data/             draft screening rules, medication catalogue, sources
  engine_validation/  synthetic test cases and validation scripts for the screening engine
frontend/           React web app
rag/                chatbot: source registry, retrieval, generation, evaluation, notebooks, tests
docs/               app screen designs and the iOS API guide
scripts/            run_all.ps1 starts the chatbot and the backend together
```

## License

No license has been chosen yet. Until one is added, all rights are reserved. The chatbot's source
documents keep their own licences (see `rag/data/source_registry.csv`).
