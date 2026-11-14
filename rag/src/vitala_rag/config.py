"""Central configuration for the VITALA RAG prototype.

Every path is derived from one project root, so the same code runs locally (VS Code), in notebooks and in Colab.
Override the root with the environment variable VITALA_ROOT.

Folder contract (raw -> processed -> indexes are strictly separated):
  data/raw/<collection-group>/   original documents exactly as received (never edited)
  data/source_registry.csv       curated registry: licence, scope, clinical review, hashes  (the activation gate)
  data/processed/                extracted pages + knowledge records (JSONL), one file per collection
  data/synthetic/                synthetic patient profiles (structured store, never mixed with medical knowledge)
  data/archive/                  backups of out-of-scope or superseded material (never indexed)
  data/eval/                     evaluation datasets (dev = tuning, test = held out)
  indexes/<collection>/          FAISS + BM25 files built from data/processed/knowledge/<collection>.jsonl
  results/                       data-quality reports and evaluation runs
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_root() -> Path:
    env = os.environ.get("VITALA_ROOT")
    if env:
        return Path(env)
    drive = Path("/content/drive/MyDrive/VITALA_RAG")
    if drive.exists():
        return drive
    # src/vitala_rag/config.py -> project root is two levels above src/
    return Path(__file__).resolve().parents[2]


@dataclass
class Paths:
    root: Path = field(default_factory=_default_root)

    # ---- raw documents (read-only inputs)
    @property
    def raw(self) -> Path: return self.root / "data" / "raw"
    @property
    def raw_pdfs(self) -> Path: return self.raw / "guidelines"          # preventive guideline PDFs
    @property
    def raw_meds(self) -> Path: return self.raw / "medications"         # FDA label JSON + medication PDFs
    @property
    def raw_app(self) -> Path: return self.raw / "app"                  # VITALA app documentation
    @property
    def registry_csv(self) -> Path: return self.root / "data" / "source_registry.csv"
    @property
    def drug_manifest(self) -> Path: return self.raw_meds / "VITALA_3_drug_source_manifest.json"
    @property
    def candidate_manifest(self) -> Path: return self.raw_meds / "candidate_drug_manifest.json"
    @property
    def app_docs(self) -> dict[str, Path]:
        """Authoritative VITALA application descriptions (Arabic), keyed by audience."""
        return {"patient": self.raw_app / "vitala_features_patient_ar.txt",
                "clinic": self.raw_app / "vitala_features_clinic_ar.txt"}
    @property
    def app_feature_status(self) -> Path: return self.raw_app / "vitala_app_feature_status.json"

    # ---- processed data
    @property
    def processed(self) -> Path: return self.root / "data" / "processed"
    @property
    def knowledge(self) -> Path: return self.processed / "knowledge"
    def knowledge_file(self, collection: str) -> Path: return self.knowledge / f"{collection}.jsonl"
    @property
    def synthetic_patients(self) -> Path: return self.root / "data" / "synthetic" / "synthetic_patients.json"
    @property
    def archive(self) -> Path: return self.root / "data" / "archive"
    @property
    def eval_dir(self) -> Path: return self.root / "data" / "eval"

    # ---- indexes and outputs
    @property
    def indexes(self) -> Path: return self.root / "indexes"
    @property
    def results(self) -> Path: return self.root / "results"
    @property
    def reports(self) -> Path: return self.results / "data_quality"      # extraction / chunk review queues
    @property
    def eval_results(self) -> Path: return self.results / "evaluation"
    @property
    def logs(self) -> Path: return self.root / "logs"

    def ensure(self) -> "Paths":
        for p in [self.raw_pdfs, self.raw_meds, self.raw_app, self.processed, self.knowledge, self.indexes,
                  self.eval_dir, self.reports, self.eval_results, self.logs]:
            p.mkdir(parents=True, exist_ok=True)
        return self


# ---- Knowledge collections -----------------------------------------------------
COLLECTION_PREVENTIVE = "preventive"   # A. preventive screening, diabetes prevention, hypertension screening/prevention
COLLECTION_MEDICATION = "medication"   # B. metformin + ACE inhibitors (class and individual agents)
COLLECTION_APP = "app"                 # C. VITALA patient app + clinic dashboard documentation
COLLECTIONS = (COLLECTION_PREVENTIVE, COLLECTION_MEDICATION)            # medical collections (HybridRetriever)
ALL_COLLECTIONS = (COLLECTION_PREVENTIVE, COLLECTION_MEDICATION, COLLECTION_APP)
# Not a knowledge collection: facts about the selected synthetic patient, cited as [P#], never medical evidence.
COLLECTION_PATIENT = "patient_context"

KB_VERSION = "2026.11.11"        # bump when the set of active sources or the chunking rules change

# ---- Medication scope (demo scope revised 2026-11-11) ---------------------------
# Only these medicines are answered from the medication collection. Everything else is declined as out of scope.
ACE_INHIBITOR_CLASS = "ace_inhibitor"
ACE_INHIBITOR_MEMBERS = ("lisinopril", "enalapril", "ramipril", "captopril", "perindopril", "benazepril", "fosinopril",
                         "quinapril", "moexipril", "trandolapril")
# Individual agents with their own monograph records in the medication collection (others: class-level only).
ACE_INHIBITORS_WITH_MONOGRAPHS = ("lisinopril", "enalapril", "ramipril", "captopril", "perindopril")
IN_SCOPE_MEDICATIONS = ("metformin", ACE_INHIBITOR_CLASS) + ACE_INHIBITOR_MEMBERS
# Removed from active retrieval (backups kept under data/archive/out_of_scope_2026-11-11/).
ARCHIVED_MEDICATIONS = ("amlodipine", "atorvastatin")

# Production switch: when true, only sources marked APPROVED by a clinical reviewer enter the active indexes.
# The demo default is false because no source has been clinically reviewed yet (see data/source_registry.csv).
REQUIRE_CLINICAL_APPROVAL = os.environ.get("VITALA_REQUIRE_CLINICAL_APPROVAL", "0") == "1"
LICENCE_STATUSES_ALLOWED = ("permitted", "permitted_internal_use")

# ---- Retrieval / model settings -------------------------------------------
EMBED_MODEL = os.environ.get("VITALA_EMBED_MODEL", "intfloat/multilingual-e5-base")
# e5 models require these prefixes (documented in the model card)
E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "

TOP_K_APP = 3
# App-collection evidence gate (keyword evidence, both retrieval modes). BM25 runs over Arabic character n-grams,
# so scores are on their own scale. Calibration 2026-11-11 on 28 Arabic questions: in-scope 7.1-29.7, out-of-scope
# (payment, language, password, video visits...) 1.8-7.9. e5 similarity did NOT separate the two groups
# (in 0.80-0.90 vs out 0.77-0.86), so it is reported in the gate details but not used as the gate.
APP_MIN_BM25 = float(os.environ.get("VITALA_APP_MIN_BM25", "8.5"))
# English questions get no Arabic n-gram overlap: lower BM25 floor, but most content words must be covered.
APP_MIN_BM25_EN = 2.0
APP_MIN_COVERAGE_EN = 0.6

CHUNK_TARGET_CHARS = 1400      # ~300-350 tokens for English medical prose
CHUNK_MAX_CHARS = 2000
CHUNK_OVERLAP_CHARS = 200
TOP_K_DENSE = 20
TOP_K_BM25 = 20
TOP_K_FINAL = 6
RRF_K = 60

# Evidence gate: if the best semantic match is below this, refuse instead of calling the LLM.
# First calibration (2026-11-10): covered questions 0.855-0.918, off-topic questions 0.797-0.803.
# Re-calibrate only on the DEV split (data/eval/dev_questions.jsonl), never on the held-out test split.
MIN_DENSE_SCORE = float(os.environ.get("VITALA_MIN_DENSE", "0.82"))
MIN_BM25_HITS_FOR_SUPPORT = 1

# ---- LLM settings ------------------------------------------------------------
# Provider: "azure_openai", "anthropic", "openai_compatible", or "extractive" (no LLM).
LLM_PROVIDER = os.environ.get("VITALA_LLM_PROVIDER", "anthropic")
ANTHROPIC_MODEL = os.environ.get("VITALA_ANTHROPIC_MODEL", "claude-opus-5-5")
ANTHROPIC_EFFORT = os.environ.get("VITALA_ANTHROPIC_EFFORT", "low")
OPENAI_COMPAT_MODEL = os.environ.get("VITALA_OPENAI_MODEL", "")
OPENAI_COMPAT_BASE_URL = os.environ.get("VITALA_OPENAI_BASE_URL", "")
LLM_MAX_TOKENS = int(os.environ.get("VITALA_LLM_MAX_TOKENS", "4000"))
# Optional pricing (USD per 1M tokens) for cost estimates in the evaluation. Unset -> cost reported as unavailable.
PRICE_INPUT_PER_1M = os.environ.get("VITALA_PRICE_INPUT_PER_1M")
PRICE_OUTPUT_PER_1M = os.environ.get("VITALA_PRICE_OUTPUT_PER_1M")

# Developer diagnostics (retrieved chunks, prompts, grounding details). Never shown to patients: the API only returns
# them when the server was started with VITALA_DEBUG=1 AND the request asks for them.
DEBUG_ALLOWED = os.environ.get("VITALA_DEBUG", "0") == "1"

PIPELINE_VERSION = "0.2.0"
