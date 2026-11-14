"""Patient-facing presentation vs developer debug mode (2026-11-12).

The grounded `answer` keeps its [E#] / [P#] markers (API, grounding, evaluation); `patient_view` and the Gradio chat show
plain text with short medical source labels; the developer panel shows everything. Offline: BM25 + fake LLMs."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vitala_rag.chatbot import (PV_TEXT, BaseLLM, ExtractiveLLM, VitalaRAG, availability_note,  # noqa: E402
                                render_patient_view, source_labels, strip_markers)
from vitala_rag.config import Paths  # noqa: E402
from vitala_rag.interfaces import (developer_panel_content, format_developer_view, format_patient_message,  # noqa: E402
                                   make_respond)
from vitala_rag.safety import EMERGENCY_MESSAGE  # noqa: E402

MARKER = re.compile(r"\[[EP]\d+\]")
TECH = ("Status:", "Source used", "collection", "chunk_id", "::", "VITALA app documentation", "evidence_gate", "rrf")
EVID_RE = re.compile(r'<evidence id="(E\d+)"[^>]*>\n(.*?)\n</evidence>', re.S)


def no_internals(text: str) -> bool:
    return not MARKER.search(text) and not any(t in text for t in TECH)


class FakeLLM(BaseLLM):
    name = "fake"

    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def generate(self, system, user, max_tokens=0):
        self.calls += 1
        return self.fn(user)

    def translate(self, q):
        return None


def cite(word, sentence):
    def f(user):
        for eid, text in EVID_RE.findall(user):
            if word.lower() in text.lower():
                return sentence.format(eid=eid)
        return "INSUFFICIENT_EVIDENCE"
    return f


@pytest.fixture(scope="module")
def rag_factory():
    if not (ROOT / "indexes/medication/index_manifest.json").exists():
        pytest.skip("indexes not built")
    return lambda llm: VitalaRAG(paths=Paths(root=ROOT), llm=llm, embedder=None, translate_queries=False, log=False)


# ------------------------------------------------------------------ deterministic marker removal
@pytest.mark.parametrize("raw,clean", [
    ("Metformin can cause diarrhea [E1]. It rarely causes low sugar [E2][E4].", "Metformin can cause diarrhea. It rarely causes low sugar."),
    ("- HbA1c: 6.9 % on 2026-04-12 [P1]", "- HbA1c: 6.9 % on 2026-04-12"),
    ("نعم، قد يسبب كحة جافة [E1] [E2].", "نعم، قد يسبب كحة جافة."),
    ("مثبطات ACE [ACE inhibitors] قد تسبب كحة [E3]", "مثبطات ACE (ACE inhibitors) قد تسبب كحة"),
])
def test_strip_markers(raw, clean):
    assert strip_markers(raw) == clean


# ------------------------------------------------------------------ app answers
APP = {"implementation_status": "unverified", "doc_status": "described"}


@pytest.mark.parametrize("chunks,expected", [
    ([APP], "unverified"), ([{**APP, "implementation_status": "implemented"}], None),
    ([{**APP, "implementation_status": "planned"}], "planned"), ([{**APP, "doc_status": "marked_possibly_not_needed"}], "not_needed"),
])
def test_availability_follows_the_status_registry(chunks, expected):
    note = availability_note(chunks, "ar")
    assert note == (PV_TEXT[expected]["ar"] if expected else None)


def test_app_answer_is_short_steps_without_documentation_citations():
    answer = ("لحجز موعد في VITALA: [E1]\n1. اختر العيادة والخدمة المطلوبة. [E1]\n2. حدد الموعد المناسب من الأوقات المتاحة. [E1]\n"
              "3. أكد الحجز، وبتلقى تفاصيله في قسم «مواعيدي». [E2]")
    cits = [{"evidence_id": "E1", "chunk_id": "VITALA-APP-PATIENT-AR::s19", "collection": "app", "source_id": "VITALA-APP-PATIENT-AR",
             "title": "VITALA patient app", "citation": "VITALA patient app - section 19", "pdf_page": None, "url": ""}]
    pv = render_patient_view("answered", "ar", "app", answer, {"kind": "app", "body": answer, "app_chunks": [APP]}, cits)
    assert pv["text"].startswith("لحجز موعد في VITALA:") and "3. أكد الحجز" in pv["text"] and no_internals(pv["text"])
    assert pv["sources"] == [] and pv["notices"] == [PV_TEXT["unverified"]["ar"]]
    msg = format_patient_message({"language": "ar", "patient_view": pv, "answer": answer})
    assert no_internals(msg) and "<details>" not in msg
    # the generic availability note is not repeated in the same conversation
    again = format_patient_message({"language": "ar", "patient_view": pv, "answer": answer},
                                   history=[{"role": "assistant", "content": msg}])
    assert PV_TEXT["unverified"]["ar"] not in again


def test_planned_feature_note_is_always_shown():
    pv = render_patient_view("answered", "en", "app", "Use the contact form [E1].",
                             {"kind": "app", "body": "Use the contact form [E1].", "app_chunks": [{**APP, "implementation_status": "planned"}]}, [])
    msg = format_patient_message({"language": "en", "patient_view": pv}, history=[{"content": PV_TEXT["planned"]["en"]}])
    assert PV_TEXT["planned"]["en"] in msg


def test_extractive_app_answer_drops_headings_and_language_note(rag_factory):
    r = rag_factory(ExtractiveLLM()).answer("كيف احجز موعد لفحص؟")
    assert r["route"] == "app" and MARKER.search(r["answer"]) and "Appointment Booking" in r["answer"]   # API unchanged
    text = r["patient_view"]["text"]
    assert no_internals(text) and "Appointment Booking" not in text and len(text.splitlines()) <= 4


def test_app_action_request_gets_one_short_line(rag_factory):
    llm = FakeLLM(cite("مواعيدي", "ادخل قسم «مواعيدي» واختر الموعد ثم اضغط إلغاء [{eid}]."))
    r = rag_factory(llm).answer("الغي موعدي لو سمحت، تقدر تلغي؟")
    pv = r["patient_view"]["text"]
    assert pv.startswith(PV_TEXT["app_action"]["ar"]) and no_internals(pv)


# ------------------------------------------------------------------ medical answers and source display
def test_medical_answer_shows_short_source_labels_and_keeps_internal_citations(rag_factory):
    llm = FakeLLM(cite("diarrhea", "Common side effects are diarrhea and nausea [{eid}]."))
    r = rag_factory(llm).answer("What are the common side effects of metformin?")
    assert r["status"] == "answered" and MARKER.search(r["answer"]) and r["citations"]       # internal citations intact
    assert r["grounding"]["verdict"] == "pass"                                               # grounding unchanged
    pv = r["patient_view"]
    assert pv["show_sources"] and no_internals(pv["text"])
    assert all(s["evidence_ids"] and s["details"] for s in pv["sources"])
    msg = format_patient_message(r)
    assert no_internals(msg.split("<details>")[0]) and "<details><summary>Source details</summary>" in msg


def test_source_labels_merge_pages_per_document():
    cits = [{"evidence_id": f"E{i}", "chunk_id": f"SA-PHA-SCPG-2023::p0{p}::000{i}", "source_id": "SA-PHA-SCPG-2023",
             "collection": "preventive", "title": "Saudi Clinical Preventive Guideline", "pdf_page": p, "section": "",
             "url": "", "citation": f"Saudi Clinical Preventive Guideline, PDF p. {p}"} for i, p in ((1, 27), (2, 30), (3, 27))]
    en, ar = source_labels(cits, "en"), source_labels(cits, "ar")
    assert len(en) == 1 and en[0]["label"].endswith("pp. 27, 30") and en[0]["evidence_ids"] == ["E1", "E2", "E3"]
    assert ar[0]["label"].startswith("الدليل الإرشادي السعودي") and "27، 30" in ar[0]["label"]
    assert source_labels([{**cits[0], "collection": "app"}], "en") == []     # app documentation is never listed


def test_quote_fallback_becomes_plain_bullets():
    body = '- "Metformin may lower vitamin B12 levels." [E2]\n- "Measure hematological parameters annually." [E2]'
    pv = render_patient_view("grounding_fallback", "en", "medical", body, {"kind": "medical", "body": body, "fallback": True}, [])
    assert pv["text"].splitlines() == [PV_TEXT["quotes"]["en"], "- Metformin may lower vitamin B12 levels.",
                                       "- Measure hematological parameters annually."]


def test_eligibility_note_is_preserved_as_a_notice():
    pv = render_patient_view("answered", "en", "medical", "Screen adults at 45 [E1].",
                             {"kind": "medical", "body": "Screen adults at 45 [E1].", "notices": ["Your plan decides."]}, [])
    assert pv["notices"] == ["Your plan decides."] and "_Your plan decides._" in format_patient_message(
        {"language": "en", "patient_view": pv})


# ------------------------------------------------------------------ safety instructions are never shortened away
@pytest.mark.parametrize("q", ["I have crushing chest pain right now", "My lips are swelling after my new lisinopril"])
def test_emergency_message_unchanged_in_patient_view(rag_factory, q):
    r = rag_factory(FakeLLM(lambda u: "x")).answer(q)
    assert r["patient_view"]["text"] == EMERGENCY_MESSAGE["en"] and "997" in format_patient_message(r)


def test_dosing_decline_and_patient_precautions_survive(rag_factory):
    rag = rag_factory(FakeLLM(lambda u: "x"))
    d = rag.answer("Should I stop taking my metformin?")
    assert d["status"] == "declined_personal_advice" and "doctor or pharmacist" in d["patient_view"]["text"]
    p = rag.answer("What was my most recent HbA1c?", patient_id="SYN-DEMO-A")
    msg = format_patient_message(p)
    assert "6.9 %" in msg and "clinician" in msg and no_internals(msg)                       # "can't interpret" kept


# ------------------------------------------------------------------ developer mode separation
def test_developer_view_has_everything_and_patient_chat_has_none_of_it(rag_factory):
    store = {}
    llm = FakeLLM(cite("diarrhea", "Common side effects are diarrhea and nausea [{eid}]."))
    respond = make_respond(rag_factory(llm), developer=True, store=store)
    chat = respond("What are the common side effects of metformin?", [], "none", "")
    assert no_internals(chat.split("<details>")[0]) and "rrf" not in chat and "dense_score" not in chat
    tech, trace = developer_panel_content(store)
    assert MARKER.search(tech)                                         # citation IDs in the developer view
    for must in ("**Status:**", "**Route:**", "FDA-LABEL-METFORMIN::", "**Evidence gate:**", "**Grounding:**",
                 "**Safety flags:**", "**Latency (ms):**"):
        assert must in tech, must
    assert trace["retrieved"] and "rrf" in trace["retrieved"][0] and trace["grounding_checks"]
    assert format_developer_view(store["last_response"]) == tech


def test_api_keeps_answer_markers_and_adds_patient_view(rag_factory):
    from fastapi.testclient import TestClient
    from vitala_rag.interfaces import app, set_rag
    set_rag(rag_factory(FakeLLM(cite("diarrhea", "Common side effects are diarrhea [{eid}]."))))
    try:
        d = TestClient(app).post("/v1/chat", json={"question": "What are the common side effects of metformin?"}).json()
        assert MARKER.search(d["answer"]) and re.fullmatch(r"E\d+", d["citations"][0]["evidence_id"])  # unchanged
        assert not MARKER.search(d["patient_view"]["text"]) and d["patient_view"]["sources"]
        assert d["debug"] is None
    finally:
        set_rag(None)


def test_internal_source_ids_in_patient_plans_become_readable_names(rag_factory):
    r = rag_factory(FakeLLM(lambda u: "INSUFFICIENT_EVIDENCE")).answer("ليش VITALA رشح لي فحص HbA1c؟", patient_id="SYN-DEMO-A")
    assert "SA-PHA-DM-2025" in r["answer"]                                   # API / developer view unchanged
    assert "SA-PHA-DM-2025" not in r["patient_view"]["text"] and "الدليل السعودي للوقاية من السكري" in r["patient_view"]["text"]
