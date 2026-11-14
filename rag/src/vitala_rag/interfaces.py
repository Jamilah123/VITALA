"""User-facing interfaces: FastAPI service, Gradio demo UI and the command-line entry point."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Literal, Optional, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from .chatbot import PV_TEXT
from .config import PIPELINE_VERSION

# ====================================================================================================
# api
# FastAPI wrapper: the integration contract between VITALA's backend and the RAG service.
#
# Run locally:   python -m vitala_rag api                (binds to 127.0.0.1:8000)
# Docs:          http://localhost:8000/docs
#
# The service is standalone: it never calls the VITALA backend and stores no patient data.
#
# Patient context (optional, synthetic only):
#   * "patient_profile_id": "SYN-DEMO-A"   select one of the built-in synthetic demo profiles (GET /v1/patients), or
#   * "patient_context": {...}             send a synthetic profile inline (must have "is_synthetic": true).
#   Sending both is rejected. Requests without either behave exactly as before (backward compatible).
#
# Developer diagnostics: "debug": true returns the pipeline trace ONLY when the server was started with
# VITALA_DEBUG=1 (never in a patient-facing deployment); otherwise the flag is ignored. POST /v1/retrieve
# (retrieval without the LLM) exists only in that mode as well.
# ====================================================================================================
class ScreeningPlanItem(BaseModel):
    """One recommendation produced by VITALA's screening engine. The chatbot explains it; it never edits it."""
    name: str = Field(..., examples=["Colorectal cancer screening"])
    status: Optional[str] = Field(None, examples=["due", "completed", "overdue", "upcoming"])
    due_date: Optional[str] = Field(None, examples=["2026-12-01"])
    # Optional fields for personalised explanations
    code: Optional[str] = Field(None, examples=["HBA1C"])
    related_codes: list[str] = Field(default_factory=list)
    name_ar: Optional[str] = None
    last_completed: Optional[str] = Field(None, examples=["2026-04-12"])
    interval: Optional[str] = None
    reason: Optional[str] = Field(None, description="Stored reason for the recommendation (as produced by VITALA)")
    reason_ar: Optional[str] = None
    guideline_reference: Optional[str] = None
    rule_id: Optional[str] = None


class Medication(BaseModel):
    name: str
    name_ar: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    since: Optional[str] = None


class PreviousResult(BaseModel):
    code: Optional[str] = Field(None, examples=["HBA1C"])
    test: str = Field(..., examples=["HbA1c"])
    test_ar: Optional[str] = None
    value: str = Field(..., examples=["6.9"])
    value_ar: Optional[str] = None
    unit: str = ""
    date: Optional[str] = Field(None, examples=["2026-04-12"])
    source: Optional[str] = None


class HistoryItem(BaseModel):
    condition: str
    condition_ar: Optional[str] = None
    since: Optional[str] = None
    status: Optional[str] = None
    relative: Optional[str] = None


class RiskFactor(BaseModel):
    factor: str
    factor_ar: Optional[str] = None


class WearableData(BaseModel):
    source: Optional[str] = None
    period: Optional[str] = None
    avg_daily_steps: Optional[float] = None
    avg_active_minutes_per_week: Optional[float] = None
    avg_sleep_hours: Optional[float] = None
    avg_resting_heart_rate_bpm: Optional[float] = None


class PatientContext(BaseModel):
    """Synthetic patient context only. Real patient data must not be sent to this prototype."""
    is_synthetic: Literal[True] = Field(..., description="Must be true. Requests with real patient data are out of scope.")
    patient_id: Optional[str] = Field(None, pattern=r"^SYN-[A-Z0-9-]{1,32}$", examples=["SYN-DEMO-A"],
                                      description="Synthetic identifier only (must start with SYN-).")
    label: Optional[str] = None
    label_ar: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=120)
    sex: Optional[Literal["male", "female"]] = None
    height_cm: Optional[float] = Field(None, ge=40, le=250)
    weight_kg: Optional[float] = Field(None, ge=2, le=400)
    bmi: Optional[float] = Field(None, ge=10, le=80)
    conditions: list[str] = Field(default_factory=list, examples=[["prediabetes"]])
    medical_history: Optional[list[HistoryItem]] = None
    family_history: Optional[list[Union[HistoryItem, str]]] = None
    medications: list[Union[Medication, str]] = Field(default_factory=list, examples=[["metformin"]])
    risk_factors: list[Union[RiskFactor, str]] = Field(default_factory=list, examples=[["family history of diabetes"]])
    screening_plan: list[ScreeningPlanItem] = Field(default_factory=list)
    recent_results: dict[str, str] = Field(default_factory=dict, examples=[{"HbA1c": "6.0%"}])
    previous_results: Optional[list[PreviousResult]] = None
    wearable_data: Optional[WearableData] = None
    data_as_of: Optional[str] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    patient_context: Optional[PatientContext] = None
    patient_profile_id: Optional[str] = Field(None, pattern=r"^SYN-[A-Z0-9-]{1,32}$", examples=["SYN-DEMO-A"],
                                              description="Select a built-in synthetic demo profile (GET /v1/patients).")
    debug: bool = Field(False, description="Developer trace; honoured only when the server runs with VITALA_DEBUG=1.")

    @model_validator(mode="after")
    def _one_context(self):
        if self.patient_context is not None and self.patient_profile_id is not None:
            raise ValueError("Send either patient_context or patient_profile_id, not both.")
        return self


class Citation(BaseModel):
    evidence_id: str
    chunk_id: str
    source_id: str
    collection: Literal["preventive", "medication", "app", "patient_context"]
    title: str
    version: str
    section: str = ""
    pdf_page: Optional[int] = None
    printed_page: str = ""
    url: str = ""
    citation: str


Status = Literal["answered", "insufficient_evidence", "emergency_escalation", "declined_personal_advice",
                 "declined_out_of_scope", "grounding_fallback", "patient_data_unavailable", "error"]


class PatientContextInfo(BaseModel):
    selected: bool
    is_synthetic: Optional[bool] = None
    patient_id: Optional[str] = None
    source: Optional[Literal["synthetic_demo_profile", "inline_synthetic_context"]] = None
    used_for: Literal["none", "background", "patient_facts"] = "none"


class ChatResponse(BaseModel):
    request_id: str
    status: Status
    language: Literal["ar", "en"]
    answer: str
    citations: list[Citation]
    retrieved_evidence_ids: list[str]
    safety_flags: list[str]
    collections_searched: list[str]
    grounding: Optional[dict] = None
    evidence_gate: Optional[dict] = None
    llm_provider: str
    disclaimer: str
    timings_ms: dict
    pipeline_version: str
    # Optional for older clients
    route: Literal["medical", "app", "patient", "patient+medical", "safety"] = "medical"
    patient_context: Optional[PatientContextInfo] = None
    # LLM accounting for every request; developer trace only in debug mode
    llm_usage: Optional[dict] = None
    debug: Optional[dict] = None
    # Patient-facing rendering of `answer` (markers removed, short source labels). `answer` itself
    # keeps the [E#] / [P#] citation markers for grounding, logging and evaluation.
    patient_view: Optional[dict] = None


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    k: int = Field(6, ge=1, le=20)


class PatientSummary(BaseModel):
    patient_id: str
    label: str
    label_ar: str = ""
    age: Optional[int] = None
    sex: Optional[str] = None
    is_synthetic: Literal[True] = True


app = FastAPI(title="VITALA RAG service (prototype)", version=PIPELINE_VERSION,
              description="Grounded answers from approved Saudi preventive guidelines, medication references for "
                          "metformin and ACE inhibitors, and the VITALA app documentation, with optional synthetic "
                          "patient context. Not a diagnostic or prescribing tool.")


def _debug_allowed() -> bool:
    return os.environ.get("VITALA_DEBUG", "0") == "1"
_rag = None


def get_rag():
    global _rag
    if _rag is None:
        from .retrieval import Embedder
        from .chatbot import VitalaRAG
        mode = os.getenv("VITALA_RETRIEVAL_MODE", "hybrid")
        if mode not in ("hybrid", "bm25"):
            raise ValueError("VITALA_RETRIEVAL_MODE must be 'hybrid' or 'bm25'")
        _rag = VitalaRAG(embedder=Embedder() if mode == "hybrid" else None)
    return _rag


def set_rag(rag) -> None:
    """Inject an already-loaded pipeline (used by notebook 04 and the tests)."""
    global _rag
    _rag = rag


@app.get("/health")
def health():
    rag = get_rag()
    return {"status": "ok", "pipeline_version": PIPELINE_VERSION, "llm_provider": rag.llm.name,
            "collections": {**{k: v.manifest["n_chunks"] for k, v in rag.retriever.indexes.items()},
                            "app": len(rag.app_kb.chunks)},
            "app_collection_loaded_from": rag.app_kb.loaded_from,
            "synthetic_patient_profiles": len(rag.list_patient_profiles()), "debug_mode": _debug_allowed()}


@app.get("/v1/patients", response_model=list[PatientSummary])
def list_patients():
    """Built-in synthetic demo profiles (synthetic test data, never real patients)."""
    return get_rag().list_patient_profiles()


@app.get("/v1/patients/{patient_id}")
def get_patient(patient_id: str):
    prof = get_rag().patients.get_profile(patient_id)
    if prof is None:
        raise HTTPException(status_code=404, detail="Unknown synthetic patient profile.")
    return prof


@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    rag = get_rag()
    if req.patient_profile_id and rag.patients.get_profile(req.patient_profile_id) is None:
        raise HTTPException(status_code=404, detail="Unknown synthetic patient profile.")
    try:
        # exclude_unset: a field the client did not send stays "not available" instead of becoming an empty list
        ctx = req.patient_context.model_dump(exclude_unset=True) if req.patient_context else None
        return rag.answer(req.question, ctx, patient_id=req.patient_profile_id, debug=req.debug and _debug_allowed())
    except Exception:
        # Avoid returning sensitive configuration or internal errors to clients.
        raise HTTPException(status_code=500, detail="The chat service could not process this request.")


@app.post("/v1/retrieve")
def retrieve(req: RetrieveRequest):
    """Developer-only: routing + retrieved chunks with scores, no LLM call. 404 unless VITALA_DEBUG=1."""
    if not _debug_allowed():
        raise HTTPException(status_code=404, detail="Not found.")
    return get_rag().retrieve_only(req.question, k=req.k)


# ====================================================================================================
# ui: Gradio chat for testing the chatbot standalone
#
# Patient mode (default) shows only `patient_view`: the answer in plain language, important notices, and - for
# medical answers - a short source line with an expandable "source details" block. No statuses, routes, collection
# names, chunk IDs or [E#] markers. Developer mode (python -m vitala_rag chat --debug) adds a separate panel with the
# technical view (status, route, citations with IDs and metadata, gate, grounding, safety flags, latency) and the
# full debug trace. The grounded `answer` with its markers is unchanged in the API and in evaluation logs.
# ====================================================================================================
STATUS_LABEL = {
    "answered": "Answered from sources", "insufficient_evidence": "Not enough evidence - declined",
    "emergency_escalation": "EMERGENCY - directed to urgent care", "declined_personal_advice": "Personal medical advice - declined",
    "declined_out_of_scope": "Out of scope", "grounding_fallback": "Quotes only (grounding check failed)",
    "patient_data_unavailable": "Patient information not available", "error": "Error",
}
ROUTE_LABEL = {"medical": "medical sources", "app": "VITALA app documentation", "patient": "synthetic patient profile",
               "patient+medical": "synthetic patient profile + medical sources", "safety": "safety rules"}
NO_CONTEXT_CHOICE = "none"
CUSTOM_CHOICE = "custom"
PATIENT_HEADER = {
    "en": "General health information from approved sources - not a diagnosis. In an emergency call **997**.",
    "ar": "معلومات صحية عامة من مصادر معتمدة، وليست تشخيصًا. في الحالات الطارئة اتصل على **997**.",
}

EXAMPLES = [
    ("When should adults start screening for colorectal cancer?", NO_CONTEXT_CHOICE),
    ("What are the common side effects of metformin?", NO_CONTEXT_CHOICE),
    ("هل يسبب الليسينوبريل كحة؟", NO_CONTEXT_CHOICE),
    ("Should metformin be stopped before a CT scan with contrast dye?", NO_CONTEXT_CHOICE),
    ("كيف احجز موعد في VITALA؟", NO_CONTEXT_CHOICE),
    ("وين ألقى نتائج فحوصاتي السابقة؟", NO_CONTEXT_CHOICE),
    ("What can the VITALA AI assistant do?", NO_CONTEXT_CHOICE),
    ("ليش VITALA رشح لي فحص HbA1c؟", "SYN-DEMO-A"),
    ("كم كانت نتيجة آخر فحص عندي؟", "SYN-DEMO-A"),
    ("What was my last HbA1c result?", "SYN-DEMO-C"),
    ("I have crushing chest pain right now", NO_CONTEXT_CHOICE),
]

SAMPLE_CONTEXT = json.dumps({
    "is_synthetic": True, "patient_id": "SYN-CUSTOM-1", "age": 52, "sex": "female", "bmi": 31.2,
    "conditions": ["prediabetes"], "medications": ["metformin"], "risk_factors": ["family history of diabetes"],
    "screening_plan": [{"name": "Colorectal cancer screening", "status": "due"},
                       {"name": "HbA1c", "status": "completed", "due_date": "2027-01-10"}],
    "recent_results": {"HbA1c": "6.0%"},
}, ensure_ascii=False, indent=1)


def _history_text(history) -> str:
    """Flatten Gradio chat history (messages or pairs) to plain text, to avoid repeating the same notice."""
    if not history:
        return ""
    parts = []
    for item in history:
        if isinstance(item, dict):
            parts.append(str(item.get("content", "")))
        elif isinstance(item, (list, tuple)):
            parts += [str(x) for x in item if x]
    return "\n".join(parts)


def format_patient_message(r: dict, history=None) -> str:
    """Patient-facing chat message, built only from r["patient_view"] (deterministic)."""
    pv = r.get("patient_view") or {"text": r.get("answer", ""), "notices": [], "sources": []}
    lang = r.get("language", "en")
    earlier = _history_text(history)
    lines = [pv["text"]]
    for n in pv.get("notices", []):
        # the generic "unverified feature" qualification is shown once per conversation, not under every answer
        if pv.get("notice_kind") == "availability_unverified" and n in earlier:
            continue
        lines.append(f"_{n}_")
    if pv.get("sources"):
        label = PV_TEXT["sources"][lang] if len(pv["sources"]) == 1 else PV_TEXT["sources_n"][lang]
        lines.append(f"<sub>{label}: " + " · ".join(s["label"] for s in pv["sources"]) + "</sub>")
        details = "<br>".join(
            "• " + "<br>&nbsp;&nbsp;".join(s["details"]) + (f'<br>&nbsp;&nbsp;<a href="{s["url"]}">{s["url"]}</a>' if s.get("url") else "")
            for s in pv["sources"])
        lines.append(f"<details><summary>{PV_TEXT['details'][lang]}</summary><sub>{details}</sub></details>")
    body = "\n\n".join(x for x in lines if x)
    return f'<div dir="rtl">\n\n{body}\n\n</div>' if lang == "ar" else body


def format_developer_view(r: dict) -> str:
    """Technical view for the developer panel: everything the patient view hides."""
    out = []
    pc = r.get("patient_context") or {}
    if pc.get("selected"):
        out.append(f"> **SYNTHETIC TEST DATA** - patient context `{pc.get('patient_id') or 'inline'}` "
                   f"(used for: {pc.get('used_for')}). This is not a real patient record.\n")
    out.append(f"**Status:** {STATUS_LABEL.get(r['status'], r['status'])} (`{r['status']}`) | "
               f"**Route:** {ROUTE_LABEL.get(r.get('route'), r.get('route'))} (`{r.get('route')}`) | "
               f"**Collections:** {', '.join(r.get('collections_searched') or []) or '-'}\n")
    out.append("**Grounded answer (with citation markers):**\n\n" + r["answer"])
    groups = {"Medical sources": ("preventive", "medication"), "VITALA app documentation": ("app",),
              "Synthetic patient profile (not medical evidence)": ("patient_context",)}
    for title, cols in groups.items():
        cits = [c for c in r["citations"] if c.get("collection") in cols]
        if cits:
            out.append(f"\n**{title}**")
            for c in cits:
                link = f" - [link]({c['url']})" if c.get("url") else ""
                out.append(f"- [{c['evidence_id']}] `{c['chunk_id']}` {c['citation']}{link}")
    g, gate = r.get("grounding") or {}, r.get("evidence_gate") or {}
    if gate:
        out.append(f"\n**Evidence gate:** {json.dumps(gate, ensure_ascii=False)}")
    if g:
        out.append(f"**Grounding:** verdict `{g.get('verdict')}` reasons {g.get('reasons')} | factual {g.get('n_factual')}, "
                   f"unsupported {g.get('n_unsupported')}, invalid citations {g.get('invalid_citations')}, "
                   f"unsupported numbers {g.get('unsupported_numbers')}")
    out.append(f"**Retrieved:** {', '.join(r.get('retrieved_evidence_ids') or []) or '-'}")
    out.append(f"**Safety flags:** {', '.join(r['safety_flags']) or '-'}")
    out.append(f"**Latency (ms):** {json.dumps(r['timings_ms'])} | **LLM:** {r['llm_provider']} {json.dumps(r.get('llm_usage'))}")
    return "\n".join(out)


# Backward-compatible name: the chat shows the patient message.
format_response = format_patient_message


def profile_choices(rag) -> list[tuple[str, str]]:
    choices = [("No patient context (general questions only)", NO_CONTEXT_CHOICE)]
    choices += [(f"{p['patient_id']} - {p['label']}", p["patient_id"]) for p in rag.list_patient_profiles()]
    choices.append(("Custom synthetic JSON (advanced)", CUSTOM_CHOICE))
    return choices


def profile_summary_md(rag, choice: str) -> str:
    if choice in (None, "", NO_CONTEXT_CHOICE):
        return "**Patient context: OFF.** Personal questions will be answered with *no profile selected*."
    if choice == CUSTOM_CHOICE:
        return ("**SYNTHETIC TEST DATA - custom JSON context.** Edit the JSON below; it must contain "
                "`\"is_synthetic\": true`.")
    p = rag.patients.get_profile(choice)
    if not p:
        return f"Unknown profile {choice}."
    plan = "; ".join(f"{it['name']} ({it.get('status')})" for it in p.get("screening_plan", []))
    meds = ", ".join(m["name"] if isinstance(m, dict) else str(m) for m in p.get("medications", [])) or "none"
    hist = ", ".join(h["condition"] for h in p.get("medical_history", [])) or "none"
    return (f"**SYNTHETIC TEST DATA - {p['patient_id']}** (not a real person)  \n"
            f"{p.get('age')} y, {p.get('sex')}, BMI {p.get('bmi')} | history: {hist} | medications: {meds}  \n"
            f"Screening plan: {plan or 'none'}")


def make_respond(rag, developer: bool = False, store: dict | None = None):
    """The chat callback, separated from the Blocks layout so tests can call it directly.

    The returned chat message is always the patient view. developer=True also keeps the full response and its debug
    trace in `store` for the developer panel; diagnostics never enter the chat."""
    store = store if store is not None else {}

    def ask(message, history, ctx=None, patient_id=None):
        r = rag.answer(message, ctx, patient_id=patient_id, debug=developer)
        store["last_response"] = r
        if developer:
            store["last"] = r.get("debug")
        return format_patient_message(r, history)

    def respond(message, history, profile_choice, ctx_text):
        if profile_choice == CUSTOM_CHOICE:
            try:
                ctx = json.loads(ctx_text) if ctx_text and ctx_text.strip() else None
            except json.JSONDecodeError as e:
                return f"Patient context is not valid JSON: {e}"
            return ask(message, history, ctx)
        if profile_choice and profile_choice != NO_CONTEXT_CHOICE:
            return ask(message, history, patient_id=profile_choice)
        return ask(message, history)
    return respond


def developer_panel_content(store: dict) -> tuple[str, dict]:
    r = store.get("last_response")
    if not r:
        return "No answer yet.", {}
    return format_developer_view(r), store.get("last") or {}


def build_demo(rag, developer: bool = False):
    """Gradio demo. The chat is always patient mode. developer=True (python -m vitala_rag chat --debug) adds a
    separate developer panel; never enable it for patients."""
    import gradio as gr

    store: dict = {}
    with gr.Blocks(title="VITALA assistant") as demo:
        gr.Markdown("## VITALA health assistant\n" + PATIENT_HEADER["en"] + "  \n" +
                    f'<span dir="rtl">{PATIENT_HEADER["ar"]}</span>\n\n'
                    "<sub>Research prototype - not clinically validated. Demo patient profiles are synthetic.</sub>")
        with gr.Row():
            profile = gr.Dropdown(choices=profile_choices(rag), value=NO_CONTEXT_CHOICE, label="Demo patient profile",
                                  info="Synthetic demo profiles for testing personal questions.", scale=2)
            banner = gr.Markdown(profile_summary_md(rag, NO_CONTEXT_CHOICE))
        with gr.Accordion("Custom synthetic patient JSON (used only when 'Custom synthetic JSON' is selected)", open=False):
            ctx_box = gr.Code(value=SAMPLE_CONTEXT, language="json", label="patient_context")
        profile.change(lambda c: profile_summary_md(rag, c), inputs=profile, outputs=banner)
        gr.ChatInterface(fn=make_respond(rag, developer, store), additional_inputs=[profile, ctx_box],
                         examples=[[q, c, SAMPLE_CONTEXT] for q, c in EXAMPLES], api_name="chat")
        if developer:
            with gr.Accordion("DEVELOPER DEBUG PANEL (never shown to patients)", open=False):
                gr.Markdown("Status, route, collections, grounded answer with citation IDs and metadata, evidence gate, "
                            "grounding check, retrieved chunks, safety flags and latency of the **last** answer, plus "
                            "the full trace (retrieval scores, prompt, raw LLM output).")
                tech = gr.Markdown()
                trace = gr.JSON(label="debug trace")
                gr.Button("Show the last answer's diagnostics").click(lambda: developer_panel_content(store),
                                                                      outputs=[tech, trace], api_name="debug_last")
    return demo


# ====================================================================================================
# cli: `python -m vitala_rag <command>`  (VS Code-friendly entry point)
#
#   doctor                      file / registry / index integrity, without loading a model or calling an API
#   build [--no-index]          stages 1-4: source gate -> extraction -> knowledge records -> FAISS + BM25 indexes
#   retrieve "question"         routing + retrieved chunks with scores, no LLM call (retrieval vs generation debugging)
#   ask "question" [--debug]    one answer in the terminal (with the developer trace when --debug)
#   trace CHUNK_ID              where a chunk came from: registry entry, file, page, URL, hashes, text-on-page check
#   evaluate --split test       retrieval + end-to-end evaluation, written to results/evaluation/<run_id>/
#   chat [--debug] / api        Gradio demo / FastAPI service on localhost only
# ====================================================================================================
def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_environment() -> None:
    # Optional convenience: install python-dotenv or use VS Code envFile support.
    try:
        from dotenv import load_dotenv
        load_dotenv(_project_root() / ".env", override=False)
    except ImportError:
        pass


def _utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")       # Arabic text in the Windows terminal
    except (AttributeError, ValueError):
        pass


def doctor() -> int:
    """Check files, the source gate and the indexes without loading an embedding model or making API calls."""
    from .config import ALL_COLLECTIONS, Paths
    from .knowledge import evaluate_registry, load_knowledge
    from .retrieval import verify_index
    _utf8_stdout()
    root = _project_root()
    paths = Paths(root=root)
    print("VITALA RAG - local project check")
    print("Project:", root)
    problems = []
    for name, path in [("source registry", paths.registry_csv), ("guideline PDFs", paths.raw_pdfs),
                       ("medication sources", paths.raw_meds), ("app documents", paths.raw_app),
                       ("synthetic patient profiles", paths.synthetic_patients),
                       ("evaluation set (dev)", paths.eval_dir / "dev_questions.jsonl"),
                       ("evaluation set (test)", paths.eval_dir / "test_questions.jsonl")]:
        ok = path.exists()
        print(f"  {'OK' if ok else 'MISSING':8} {name}")
        if not ok:
            problems.append(name)
    try:
        decisions = evaluate_registry(paths, scan=False)
        active = [d for d in decisions if d.active]
        print(f"  OK       source gate: {len(active)} active / {len(decisions)} registered sources")
        for d in decisions:
            if not d.active:
                print(f"           inactive {d.source_id}: {'; '.join(d.reasons)[:110]}")
        broken = [d for d in decisions if d.checks.get("file_present") and d.checks.get("sha256_matches_registry") is False]
        for d in broken:
            print(f"  CHECK    {d.source_id}: file changed since registration")
            problems.append(f"{d.source_id} hash")
    except (OSError, ValueError, KeyError) as exc:
        print(f"  CHECK    source registry: {type(exc).__name__}: {exc}")
        problems.append("registry")
    for col in ALL_COLLECTIONS:
        v = verify_index(paths.indexes / col)
        if not v["ok"]:
            print(f"  CHECK    {col} index: {v.get('error') or v}")
            problems.append(f"{col} index")
            continue
        try:
            n_active = len(load_knowledge(paths, col))
            synced = n_active == v["n_chunks"]
        except OSError:
            n_active, synced = None, False
        print(f"  {'OK' if synced else 'WARNING':8} {col} index: {v['n_chunks']} chunks (knowledge records active: "
              f"{n_active}; kb {v.get('kb_version')})")
        if not synced:
            print("           the knowledge records changed after the index was built: run `python -m vitala_rag build`")
    try:
        from .patient_context import SyntheticPatientProvider
        from .retrieval import AppKnowledgeBase
        kb = AppKnowledgeBase(paths)
        print(f"  {'OK' if kb.chunks else 'CHECK':8} app collection: {len(kb.chunks)} sections ({kb.index_note})")
        n_pat = len(SyntheticPatientProvider(paths.synthetic_patients).list_profiles())
        print(f"  {'OK' if n_pat else 'CHECK':8} synthetic patient profiles: {n_pat}")
    except (ImportError, OSError, ValueError) as exc:
        print(f"  CHECK    app collection / synthetic profiles: {type(exc).__name__}: {exc}")
    for pkg in ("rank_bm25", "sentence_transformers", "faiss", "gradio", "fastapi", "uvicorn", "openai", "anthropic",
                "matplotlib", "nbformat"):
        print(f"  {'OK' if importlib.util.find_spec(pkg) else 'NOT INSTALLED':13} Python module: {pkg}")
    print("  LLM provider:", os.environ.get("VITALA_LLM_PROVIDER", "(not set)"), "| API keys are not checked or printed.")
    if problems:
        print("Check:", ", ".join(problems))
        return 1
    return 0


def _make_rag(retrieval: str, provider: str):
    from .chatbot import VitalaRAG, get_llm
    from .retrieval import Embedder
    embedder = Embedder() if retrieval == "hybrid" else None
    return VitalaRAG(embedder=embedder, llm=get_llm(provider), translate_queries=provider != "extractive")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m vitala_rag", description="Run or diagnose the VITALA RAG prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check files, the source gate and the indexes")
    b = sub.add_parser("build", help="Stages 1-4: gate, extraction, knowledge records, indexes")
    b.add_argument("--no-index", action="store_true", help="Stop after the knowledge records (no embedding model)")
    t = sub.add_parser("trace", help="Trace a chunk back to its source document and page")
    t.add_argument("chunk_id")

    def common(p, provider_default="extractive"):
        p.add_argument("--retrieval", choices=("bm25", "hybrid"), default="hybrid",
                       help="hybrid = e5 + FAISS + BM25 (downloads the e5 model once); bm25 = keyword only")
        p.add_argument("--provider", choices=("extractive", "anthropic", "azure_openai", "openai_compatible"),
                       default=provider_default, help="extractive works without LLM API keys")
    r = sub.add_parser("retrieve", help="Retrieval only (no LLM): route, chunks, scores")
    r.add_argument("question")
    r.add_argument("-k", type=int, default=6)
    common(r)
    a = sub.add_parser("ask", help="Answer one question in the terminal")
    a.add_argument("question")
    a.add_argument("--patient", default=None, help="synthetic profile id, e.g. SYN-DEMO-A")
    a.add_argument("--debug", action="store_true", help="print the developer trace")
    common(a, os.environ.get("VITALA_LLM_PROVIDER", "extractive"))
    e = sub.add_parser("evaluate", help="Run the evaluation and write results/evaluation/<run_id>/")
    e.add_argument("--split", choices=("dev", "test", "all"), default="test")
    e.add_argument("--retrieval-only", action="store_true", help="skip the end-to-end (LLM) pass")
    e.add_argument("--judge", action="store_true", help="add automated LLM-judge ratings (extra LLM calls)")
    common(e, os.environ.get("VITALA_LLM_PROVIDER", "extractive"))
    for command in ("chat", "api"):
        run = sub.add_parser(command, help=f"Start {command} locally (never a public share link)")
        common(run)
        run.add_argument("--debug", action="store_true", help="developer diagnostics (never for patients)")
    args = parser.parse_args(argv)
    _load_environment()
    _utf8_stdout()
    if args.command == "doctor":
        raise SystemExit(doctor())
    from .config import Paths
    paths = Paths(root=_project_root())
    if args.command == "build":
        from .knowledge import build_all
        from .retrieval import Embedder
        out = build_all(paths, None if args.no_index else Embedder())
        print(json.dumps({"active_sources": out["gate"]["active"], "inactive": out["gate"]["inactive"],
                          "knowledge": out["knowledge"]["collections"],
                          "indexes": {c: m["n_chunks"] for c, m in out.get("indexes", {}).items()}}, indent=1))
        return
    if args.command == "trace":
        from .knowledge import trace_chunk
        print(json.dumps(trace_chunk(paths, args.chunk_id), indent=1, ensure_ascii=False))
        return
    if hasattr(args, "debug") and args.debug:
        os.environ["VITALA_DEBUG"] = "1"
    os.environ["VITALA_RETRIEVAL_MODE"] = args.retrieval
    os.environ["VITALA_LLM_PROVIDER"] = args.provider
    if args.command == "api":
        import uvicorn
        uvicorn.run("vitala_rag.interfaces:app", host="127.0.0.1", port=8000, reload=False)
        return
    rag = _make_rag(args.retrieval, args.provider)
    if args.command == "retrieve":
        out = rag.retrieve_only(args.question, k=args.k)
        print(f"route={out['route']} collections={out['collections']} medications={out['medications']} "
              f"gate={out['evidence_gate']} timings={out['timings_ms']}")
        for c in out["candidates"]:
            print(f"{c['rank']:2d}. {c['chunk_id']:55s} dense={c['dense_score']} bm25={c['bm25_score']} "
                  f"rrf={c['rrf']} | {c['section'][:60]}")
    elif args.command == "ask":
        r = rag.answer(args.question, patient_id=args.patient, debug=args.debug)
        print(f"[{r['status']} | route {r['route']} | {r['timings_ms'].get('total')} ms | {r['llm_usage']}]\n")
        print(r["answer"])
        for c in r["citations"]:
            print(f"  [{c['evidence_id']}] {c['citation']}")
        if args.debug:
            print("\n--- DEBUG TRACE (developer only) ---")
            print(json.dumps(r.get("debug"), indent=1, ensure_ascii=False, default=str)[:20000])
    elif args.command == "evaluate":
        from .evaluation import load_questions, run_evaluation
        qs = []
        for split in (("dev", "test") if args.split == "all" else (args.split,)):
            qs += load_questions(paths.eval_dir / f"{split}_questions.jsonl")
        judge = rag.llm if args.judge and args.provider != "extractive" else None
        res = run_evaluation(rag, qs, paths.eval_results, args.split, end_to_end=not args.retrieval_only, judge_llm=judge)
        print("Results:", res["dir"])
    elif args.command == "chat":
        build_demo(rag, developer=args.debug).launch(server_name="127.0.0.1", server_port=7860, share=False)


if __name__ == "__main__":
    main()
