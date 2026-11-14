"""VITALA app knowledge base: parsing, metadata, routing, retrieval, gate, availability notes (offline)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vitala_rag.chatbot import app_status_notes, extractive_app_answer  # noqa: E402
from vitala_rag.knowledge import load_feature_status, parse_app_document  # noqa: E402
from vitala_rag.retrieval import AppKnowledgeBase  # noqa: E402
from vitala_rag.config import Paths  # noqa: E402
from vitala_rag.retrieval import app_intent, is_app_action_request, process_query  # noqa: E402

PATIENT_DOC = ROOT / "data/raw/app/vitala_features_patient_ar.txt"
CLINIC_DOC = ROOT / "data/raw/app/vitala_features_clinic_ar.txt"


@pytest.fixture(scope="module")
def kb():
    return AppKnowledgeBase(Paths(root=ROOT))


def _top(kb, q):
    return kb.search(q).candidates[0].chunk


# ------------------------------------------------------------------ parsing + metadata
def test_documents_split_into_numbered_sections_with_metadata(kb):
    ids = [c["chunk_id"] for c in kb.chunks]
    assert len(ids) == len(set(ids)) == 32                       # patient 2-24 (23) + clinic 25-33 (9)
    assert ids[0] == "VITALA-APP-PATIENT-AR::s02" and ids[-1] == "VITALA-APP-CLINIC-AR::s33"
    c = next(c for c in kb.chunks if c["chunk_id"].endswith("::s19"))
    assert c["collection"] == "app" and c["section_title_en"] == "Appointment Booking"
    assert c["filename"] == "vitala_features_patient_ar.txt" and len(c["sha256"]) == 64
    assert "section 19: Appointment Booking" in c["citation"]
    assert c["text"].startswith("19. حجز الموعد (Appointment Booking)")
    # each section holds only its own text (the next header is not swallowed)
    assert "20." not in c["text"]


def test_not_needed_markings_are_preserved(kb):
    by = {c["chunk_id"]: c for c in kb.chunks}
    assert by["VITALA-APP-PATIENT-AR::s21"]["doc_status"] == "marked_possibly_not_needed"   # Contact Clinic
    assert by["VITALA-APP-CLINIC-AR::s33"]["doc_status"] == "marked_possibly_not_needed"    # Contact Requests
    assert by["VITALA-APP-PATIENT-AR::s22"]["doc_status"] == "described"                    # block closed again
    s18 = by["VITALA-APP-PATIENT-AR::s18"]
    assert s18["has_inline_not_needed_notes"] and "(ما يحتاج" not in s18["text"] and "قد لا تكون" in s18["text"]


def test_implementation_status_defaults_to_unverified(kb):
    assert {c["implementation_status"] for c in kb.chunks} == {"unverified"}


def test_feature_status_override_file(tmp_path):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"default_status": "unverified", "sections": {
        "VITALA-APP-PATIENT-AR::s19": {"status": "implemented"}, "VITALA-APP-PATIENT-AR::s07": {"status": "planned"}}}))
    chunks = {c["chunk_id"]: c for c in parse_app_document(PATIENT_DOC, "patient", load_feature_status(status))}
    assert chunks["VITALA-APP-PATIENT-AR::s19"]["implementation_status"] == "implemented"
    assert chunks["VITALA-APP-PATIENT-AR::s07"]["implementation_status"] == "planned"
    # a verified section needs no "unverified" note; a planned one says so
    assert app_status_notes([chunks["VITALA-APP-PATIENT-AR::s19"]], "en") == ""
    assert "planned" in app_status_notes([chunks["VITALA-APP-PATIENT-AR::s07"]], "en")
    status.write_text(json.dumps({"default_status": "available"}))
    with pytest.raises(ValueError):
        load_feature_status(status)


def test_missing_documents_give_an_empty_collection(tmp_path):
    kb = AppKnowledgeBase(Paths(root=tmp_path))
    assert not kb.available and len(kb.missing_docs) == 2
    assert kb.search("كيف احجز موعد؟").gate["passed"] is False


# ------------------------------------------------------------------ Arabic + Saudi dialect app questions
@pytest.mark.parametrize("q,section", [
    ("كيف احجز موعد لفحص؟", "Appointment Booking"),
    ("وين ألقى نتائج فحوصاتي السابقة؟", "Results & Health History"),
    ("كيف أعدل أو ألغي موعدي؟", "Booking Confirmation & My Appointments"),
    ("وش الفرق بين الفحوصات المستحقة والمتأخرة؟", "Health Plan Summary"),
    ("كيف اربط Apple Health؟", "Wearable Device Integration"),
    ("هل العيادة تقدر تشوف معلوماتي؟", "Patients Management"),
    ("كيف يستخدم VITALA معلوماتي الصحية؟", "Health Data Analysis"),
    ("ابغى الغي الحجز", "Booking Confirmation & My Appointments"),
    ("كيف أشوف العيادات القريبة مني؟", "Nearby Clinics"),
    ("وش يسوي المساعد الذكي؟", "VITALA AI Assistant"),
])
def test_arabic_app_questions_retrieve_the_right_section(kb, q, section):
    res = kb.search(q)
    assert res.gate["passed"], res.gate
    assert res.candidates[0].chunk["section_title_en"] == section


# ------------------------------------------------------------------ English app questions
@pytest.mark.parametrize("q,section", [
    ("What can the VITALA AI assistant do?", "VITALA AI Assistant"),
    ("How do I cancel my appointment?", "Booking Confirmation & My Appointments"),
    ("How do I connect my smartwatch?", "Wearable Device Integration"),
    ("Where can I see my previous results?", "Results & Health History"),
])
def test_english_app_questions_retrieve_the_right_section(kb, q, section):
    res = kb.search(q)
    assert res.gate["passed"], res.gate
    assert res.candidates[0].chunk["section_title_en"] == section


@pytest.mark.parametrize("q", [
    "How do I pay for my appointment?", "What is the app privacy policy?", "Does VITALA support video consultations with doctors?",
    "كيف أغير لغة التطبيق؟", "هل أقدر أدفع بالتطبيق؟", "كيف أغير كلمة المرور؟", "هل التطبيق مجاني؟",
])
def test_topics_absent_from_the_documents_fail_the_gate(kb, q):
    """No invented features: payment, privacy policy, video visits, language settings... are not documented."""
    assert kb.search(q).gate["passed"] is False


# ------------------------------------------------------------------ routing
@pytest.mark.parametrize("q", [
    "كيف احجز موعد لفحص؟", "وين ألقى نتائج فحوصاتي السابقة؟", "كيف أعدل أو ألغي موعدي؟", "كيف اربط Apple Health؟",
    "هل العيادة تقدر تشوف معلوماتي؟", "كيف يستخدم VITALA معلوماتي الصحية؟", "What can the VITALA AI assistant do?",
    "How do I book a colonoscopy?", "احجز لي موعد بكرة",
])
def test_app_navigation_routes_only_to_app_collection(q):
    pq = process_query(q)
    assert pq.app_intent == "nav" and pq.collections == ["app"]


def test_app_topic_routing():
    assert process_query("وش الفرق بين الفحوصات المستحقة والمتأخرة؟").collections == ["app"]
    assert process_query("What is the difference between due and overdue screenings?").app_intent == "topic"


def test_every_existing_evaluation_question_keeps_its_medical_route():
    for line in (ROOT / "data/eval/dev_questions.jsonl").read_text(encoding="utf-8").splitlines():
        if json.loads(line)["id"].startswith("dev-probe"):      # later probe questions include app / patient ones
            continue
        q = json.loads(line)["question"]
        assert app_intent(q) is None, q
        assert "app" not in process_query(q).collections, q


@pytest.mark.parametrize("q,cols", [
    ("How do I lower my blood pressure?", ["preventive"]),
    ("How can I find out if I have diabetes?", ["preventive"]),
    ("كيف يستخدم الميتفورمين؟", ["medication"]),
    ("Why does VITALA recommend HbA1c for me?", ["preventive"]),     # a reason question, not navigation
])
def test_medical_questions_that_look_like_how_to_stay_medical(q, cols):
    assert process_query(q).collections[:1] == cols


def test_action_requests_are_detected():
    assert is_app_action_request("احجز لي موعد بكرة") and is_app_action_request("Can you book an appointment for me?")
    assert not is_app_action_request("How do I book an appointment?")


# ------------------------------------------------------------------ answer helpers
def test_extractive_app_answer_quotes_with_markers(kb):
    res = kb.search("كيف احجز موعد لفحص؟")
    ev = [{"eid": f"E{i}", "chunk": c.chunk, "text": c.chunk["text"], "collection": "app", "bm25": c.bm25_score}
          for i, c in enumerate(res.candidates, 1)]
    out = extractive_app_answer(ev, "ar")
    assert out.startswith("**19. حجز الموعد (Appointment Booking)** [E1]") and "[E1]" in out
    en = extractive_app_answer(ev, "en")
    assert en.startswith("Note:")


def test_status_notes_for_unverified_and_not_needed_sections(kb):
    by = {c["chunk_id"]: c for c in kb.chunks}
    note = app_status_notes([by["VITALA-APP-PATIENT-AR::s21"]], "en")
    assert "has not been verified" in note and "possibly not needed" in note
    ar = app_status_notes([by["VITALA-APP-PATIENT-AR::s18"]], "ar")
    assert "لم يتم التحقق" in ar and "بعض البنود" in ar
