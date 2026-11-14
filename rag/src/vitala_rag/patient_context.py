"""Patient context: synthetic demo profiles now, VITALA's authenticated backend later.

Design rules (they keep personalised answers safe):
  1. Patient facts are rendered by code from the structured profile, never written by the LLM. The rendered
     lines carry [P#] markers that point to "patient records", so the grounding checker can verify any patient
     value an LLM repeats ([P#] numbers must appear in the cited record).
  2. Patient records are facts about one synthetic person. They are never medical evidence: medical claims must
     cite the indexed guidelines / FDA labels ([E#]).
  3. The chatbot explains the screening plan VITALA stored; it never creates a recommendation, changes a status
     or decides eligibility. A test that is not in the plan is reported as "not in your plan".
  4. Missing data is reported as missing. Nothing is estimated or filled in.

Integration point: implement PatientContextProvider for the real backend (see VitalaBackendPatientProvider) and
pass it to VitalaRAG(patient_provider=...). The rest of the pipeline only sees the normalised profile dict.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import COLLECTION_PATIENT, Paths
from .retrieval import normalize_arabic

SYNTHETIC_ID_RE = re.compile(r"^SYN-[A-Z0-9-]{1,32}$")

# ------------------------------------------------------------------ test vocabulary
# code -> display names + aliases (English / Arabic incl. Saudi dialect). Aliases are matched longest-first.
TEST_CATALOG = {
    "HBA1C": ("HbA1c", "السكر التراكمي (HbA1c)",
              ["hba1c", "hb a1c", "a1c", "glycated", "glycosylated", "السكر التراكمي", "سكر تراكمي", "التراكمي"]),
    "FPG": ("Fasting plasma glucose", "سكر الدم الصائم",
            ["fasting plasma glucose", "fasting glucose", "fasting blood sugar", "fasting sugar", "fpg",
             "السكر الصائم", "سكر صائم", "سكر الصيام", "الصايم"]),
    "BP": ("Blood pressure", "ضغط الدم", ["blood pressure", "bp", "ضغط الدم", "الضغط", "ضغطي", "ضغط"]),
    "LIPID": ("Lipid profile / cholesterol", "الدهون / الكوليسترول",
              ["lipid profile", "lipids", "lipid", "cholesterol", "ldl", "الكوليسترول", "كوليسترول", "كولسترول",
               "الدهون", "تحليل الدهون"]),
    "EGFR": ("eGFR (kidney function)", "وظائف الكلى (eGFR)",
             ["egfr", "kidney function", "creatinine", "وظائف الكلى", "الكلى", "كلى"]),
    "UACR": ("UACR (urine albumin)", "الألبومين في البول (UACR)", ["uacr", "albumin", "الالبومين", "الزلال"]),
    "EYE": ("Eye exam", "فحص العين", ["eye exam", "eye", "retinopathy", "retina", "فحص العين", "العين", "عيوني", "الشبكيه"]),
    "MAMMO": ("Mammogram", "الماموجرام", ["mammogram", "mammography", "breast", "الماموجرام", "ماموجرام", "الثدي"]),
    "CRC": ("Colorectal cancer screening", "فحص سرطان القولون",
            ["colorectal", "colon", "bowel", "fit test", "القولون", "سرطان القولون"]),
    "SMOKING": ("Smoking cessation", "الإقلاع عن التدخين", ["smoking", "tobacco", "cigarette", "التدخين", "الدخان"]),
    "DM_SCREEN": ("Diabetes screening", "فحص السكري",
                  ["diabetes screening", "diabetes", "blood sugar", "sugar", "السكري", "سكري", "السكر", "سكر"]),
}
# A code in a question also matches these result / plan codes.
CODE_GROUPS = {"DM_SCREEN": {"DM_SCREEN", "HBA1C", "FPG"}, "LIPID": {"LIPID", "LDL", "HDL", "TC", "TG"},
               "CRC": {"CRC", "FIT"}, "EGFR": {"EGFR"}, "UACR": {"UACR"}}
_ALIASES = sorted(((normalize_arabic(a.lower()), code) for code, (_, _, al) in TEST_CATALOG.items() for a in al),
                  key=lambda x: -len(x[0]))

STATUS_LABEL = {
    "en": {"due": "due", "overdue": "overdue", "upcoming": "upcoming", "completed": "completed"},
    "ar": {"due": "مستحق", "overdue": "متأخر", "upcoming": "قادم", "completed": "مكتمل"},
}


def find_test_codes(text: str) -> list[str]:
    """Test codes mentioned in a question ("السكر التراكمي" -> HBA1C, "cholesterol" -> LIPID)."""
    t = " " + normalize_arabic(text.lower()) + " "
    found = []
    for alias, code in _ALIASES:
        pat = rf"(?<!\w)(ال|و|بال|لل)?{re.escape(alias)}(?!\w)" if not alias.isascii() else rf"\b{re.escape(alias)}\b"
        if re.search(pat, t):
            if code not in found:
                found.append(code)
            t = re.sub(pat, " ", t)
    return found


def expand_codes(codes: list[str]) -> set[str]:
    out = set()
    for c in codes:
        out |= CODE_GROUPS.get(c, {c})
    return out


# ------------------------------------------------------------------ question intent
# Whole-word boundaries. Unicode \w covers Arabic letters but not Arabic punctuation such as "؟" and "،"
# (a [؀-ۿ] class would wrongly treat "عندي؟" as one word).
_AR_START, _AR_END = r"(?<!\w)", r"(?!\w)"
_PERSONAL = re.compile(
    r"\b(my|me|mine|i|i'm|i've|did i|do i|am i)\b|" + _AR_START + "(و|ف)?(" + normalize_arabic(
        r"عندي|لي|حقتي|حقي|نتيجتي|نتايجي|نتائجي|فحوصاتي|ادويتي|أدويتي|خطتي|وزني|طولي|عمري|خطواتي|نومي|ضغطي|مني|علي|"
        r"سويت|سويته|اخذها|آخذها|استخدمها|ملفي|امراضي|أمراضي|تحاليلي") + ")" + _AR_END, re.I)
# Advice-seeking ("how can I lower my weight?") is a general medical question, not a profile lookup.
_ADVICE_RE = re.compile(
    r"\b(how (can|do|should) i (lower|reduce|lose|improve|increase|raise|control|prevent|manage)|lower|reduce|lose|"
    r"improve|prevent)\b|" + normalize_arabic(r"كيف (انزل|أنزل|اخفض|أخفض|اقلل|أقلل|احسن|أحسن|اخفف|أخفف|اتحكم|أتحكم|امنع)|"
                                              r"انزل|اخفض|انقص|احسن"), re.I)
_LAST_AR = _AR_START + normalize_arabic(r"(اخر|آخر|احدث|أحدث|السابق|السابقه|الاخير|الاخيره|الأخيرة)")
_INTENTS = [
    ("recommendation_reason", re.compile(
        r"\bwhy\b.{0,80}\b(recommend\w*|suggest\w*|need|plan|due|overdue|have to|should|scheduled|listed)\b|"
        r"\breason\b.{0,40}\b(recommend\w*|for my|in my)\b|" + normalize_arabic(
            r"(ليش|لماذا|ليه|لمذا|وش السبب|ايش السبب|ما سبب|سبب).{0,60}(رشح|يرشح|ترشح|رشحت|اوصى|أوصى|يوصي|توصيه|"
            r"توصية|طلب|مطلوب|لازم|خطتي|الخطه|موصى|مستحق|متاخر|محتاج|احتاج)"), re.I)),
    ("plan", re.compile(
        r"\bmy (screening |health )?plan\b|\b(tests?|screenings?) (are |is )?(due|overdue|upcoming|recommended|scheduled)"
        r" for me\b|\bmy (due|overdue|upcoming|recommended|next) (tests?|screenings?)\b|\bwhat (tests?|screenings?) "
        r"(do i have|are due|are overdue|are on my|should i do next)\b|" + normalize_arabic(
            r"خطتي|خطه الفحوصات حقتي|خطه فحوصاتي|فحوصاتي (المستحقه|المتاخره|القادمه|الجايه)|الفحوصات (المستحقه|المتاخره|"
            r"القادمه|الجايه|المطلوبه|الموصى بها) (عندي|لي|علي|مني)|وش الفحوصات (اللي|الي) (علي|عندي|لازم|مطلوبه)|"
            r"(وش|ايش) (عندي|علي) من فحوصات"), re.I)),
    ("results_history", re.compile(
        r"\b(all|history of|list) (of )?my .{0,25}(results|readings|tests)\b|\bmy .{0,20}(results|readings) over time\b|"
        + normalize_arabic(r"كل نتائجي|جميع نتائجي|تاريخ نتائجي|كل نتايجي|كل قراءات"), re.I)),
    ("latest_result", re.compile(
        r"\b(last|latest|most recent|recent|previous|newest)\b.{0,40}\b(results?|tests?|readings?|labs?|levels?|values?|"
        r"hba1c|a1c|glucose|pressure|cholesterol|ldl|egfr|uacr|mammogram)\b|\bwhat (was|were|is|are) my\b.{0,40}"
        r"\b(results?|levels?|readings?|values?|hba1c|a1c|glucose|pressure|cholesterol|ldl|egfr|uacr)\b|"
        + _LAST_AR + normalize_arabic(r".{0,30}(نتيجه|نتائج|نتايج|فحص|تحليل|قراءه|قياس)|")
        + normalize_arabic(r"(نتيجه|نتائج|نتايج|قراءه|قياس|تحليل).{0,30}") + _LAST_AR + "|" + normalize_arabic(
            r"كم (كان|كانت|طلع|طلعت|صار).{0,40}(نتيجه|قراءه|مستوى|التراكمي|الضغط|السكر|الكوليسترول|تحليل)|"
            r"نتيجتي|نتيجه (فحصي|تحليلي)"), re.I)),
    ("medications", re.compile(
        r"\bmy (current )?(medications?|meds|medicines?|drugs?|prescriptions?)\b|\bwhat (medications?|meds|medicines?|drugs?)"
        r" (am i|do i)\b|" + normalize_arabic(
            r"ادويتي|أدويتي|علاجاتي|الادويه (اللي|الي) (اخذها|آخذها|استخدمها|استعملها)|(وش|ايش) الادويه (حقتي|اللي|الي)|"
            r"ادويه حقتي"), re.I)),
    ("conditions", re.compile(
        r"\bmy (medical history|conditions?|diagnos[ie]s|diseases?|health problems?)\b|" + normalize_arabic(
            r"امراضي|أمراضي|تاريخي المرضي|التاريخ المرضي (حقي|لي|عندي)|(وش|ايش) امراضي"), re.I)),
    ("family_history", re.compile(
        r"\bmy family (medical )?history\b|" + normalize_arabic(r"تاريخ عائلتي|التاريخ العائلي|التاريخ المرضي للعائله"), re.I)),
    ("risk_factors", re.compile(
        r"\bmy risk factors?\b|" + normalize_arabic(r"عوامل الخطوره (عندي|حقتي|لي)|عوامل الخطر (عندي|حقتي|لي)"), re.I)),
    ("wearable", re.compile(
        r"\bmy (steps|sleep|heart rate|activity|active minutes|wearable( data)?|watch data)\b|" + normalize_arabic(
            r"خطواتي|نومي|نبضي|نشاطي|معدل ضربات قلبي|بيانات (من )?(ال)?(ساعه|ساعتي|جهاز)"), re.I)),
    ("profile", re.compile(
        r"\bmy (current |latest |recorded )?(bmi|weight|height|age|body mass index)\b|\bhow (much do i weigh|tall am i|old am i)\b|" + normalize_arabic(
            r"وزني|طولي|عمري|مؤشر كتله جسمي|كتله الجسم (حقتي|عندي)|(كم|وش) (ال)?bmi"), re.I)),
]
_MEANING_RE = re.compile(
    r"\b(mean|means|meaning|normal|high|low|good|bad|interpret\w*|explain|ok|okay|worry)\b|" + normalize_arabic(
        r"معنى|معناها|معناه|يعني|طبيعي|طبيعيه|مرتفع|مرتفعه|عالي|عاليه|منخفض|زين|زينه|كويس|كويسه|سيء|اشرح|فسر|اقلق"), re.I)
_STATUS_WORDS = {
    "overdue": re.compile(r"\boverdue\b|" + normalize_arabic("متاخر|المتاخره|متاخره|فات موعد"), re.I),
    "due": re.compile(r"\bdue\b(?! to)|" + normalize_arabic("مستحق|المستحقه|مستحقه"), re.I),
    "upcoming": re.compile(r"\b(upcoming|next)\b|" + normalize_arabic("القادمه|قادم|الجايه|الجاي"), re.I),
}


@dataclass
class PatientIntent:
    kind: str                         # see _INTENTS
    codes: list[str] = field(default_factory=list)
    wants_meaning: bool = False       # "...and what does it mean?" -> also needs medical evidence
    statuses: list[str] = field(default_factory=list)

    @property
    def needs_medical_evidence(self) -> bool:
        return self.kind == "recommendation_reason" or (self.kind in ("latest_result", "results_history")
                                                         and self.wants_meaning)


def detect_patient_intent(question: str, eligibility_flag: bool = False) -> PatientIntent | None:
    """Is this a question about the selected patient's own data? Returns None for general questions."""
    t = normalize_arabic(question.lower())
    codes = find_test_codes(question)
    personal = bool(_PERSONAL.search(t))
    statuses = [s for s, rx in _STATUS_WORDS.items() if rx.search(t)]
    advice = bool(_ADVICE_RE.search(t))
    for kind, rx in _INTENTS:
        if not rx.search(t):
            continue
        if advice and kind != "recommendation_reason":
            return None
        # "Why does VITALA recommend HbA1c tests?" is answerable from the plan even without "my".
        if not personal and not (kind == "recommendation_reason" and re.search(r"vitala|فيتالا", t)):
            continue
        return PatientIntent(kind, codes, bool(_MEANING_RE.search(t)) and kind != "recommendation_reason", statuses)
    if eligibility_flag and codes:
        # "Do I need an HbA1c test?" -> explain what the stored plan says; never decide eligibility.
        return PatientIntent("recommendation_reason", codes)
    return None


# ------------------------------------------------------------------ providers
class PatientContextProvider(Protocol):
    """Source of patient profiles. Every returned profile must be a dict in the normalised schema."""

    def list_profiles(self) -> list[dict]: ...

    def get_profile(self, patient_id: str) -> dict | None: ...


class SyntheticPatientProvider:
    """Demo profiles from data/synthetic_patients/synthetic_patients.json (synthetic data only)."""

    def __init__(self, path: Path | None = None):
        self.path = path or Paths().synthetic_patients
        self.profiles: dict[str, dict] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for p in data.get("profiles", []):
                if p.get("is_synthetic") is not True or not SYNTHETIC_ID_RE.match(str(p.get("patient_id", ""))):
                    raise ValueError(f"{self.path.name}: every profile needs is_synthetic=true and an SYN- id")
                self.profiles[p["patient_id"]] = p

    def list_profiles(self) -> list[dict]:
        return [{"patient_id": p["patient_id"], "label": p.get("label", ""), "label_ar": p.get("label_ar", ""),
                 "age": p.get("age"), "sex": p.get("sex"), "is_synthetic": True} for p in self.profiles.values()]

    def get_profile(self, patient_id: str) -> dict | None:
        p = self.profiles.get(patient_id)
        return json.loads(json.dumps(p)) if p else None      # defensive copy


class VitalaBackendPatientProvider:
    """Placeholder for the authenticated VITALA backend. Intentionally not implemented in this prototype.

    Before enabling it: authentication of the end user, consent, transport encryption, audit logging, data
    minimisation (send only the fields in the normalised schema), removal of the `is_synthetic` requirement
    in safety.sanitize_patient_context, clinical sign-off, and a privacy review. Until then the RAG service
    must only ever see synthetic profiles.
    """

    def __init__(self, *_, **__):
        raise NotImplementedError("Real patient data is out of scope for this prototype; use SyntheticPatientProvider.")


# ------------------------------------------------------------------ normalisation
def guess_code(name: str) -> str | None:
    codes = find_test_codes(name or "")
    return codes[0] if codes else None


def normalize_profile(ctx: dict) -> dict:
    """Accept the legacy context shape (conditions: [str], medications: [str], recent_results: {name: value})
    and the full profile shape; return the full shape. Absent sections stay absent (= not available)."""
    p = dict(ctx)
    if "conditions" in p and "medical_history" not in p:
        p["medical_history"] = [{"condition": c} for c in p.get("conditions") or []]
    p["medications"] = [m if isinstance(m, dict) else {"name": str(m)} for m in p.get("medications") or []] \
        if "medications" in p else None
    if p["medications"] is None:
        p.pop("medications")
    for key, field_name in (("risk_factors", "factor"), ("family_history", "condition")):
        if key in p:
            p[key] = [x if isinstance(x, dict) else {field_name: str(x)} for x in p.get(key) or []]
    if "recent_results" in p and "previous_results" not in p:
        p["previous_results"] = [{"code": guess_code(k), "test": k, "value": str(v), "unit": "", "date": None}
                                 for k, v in (p.get("recent_results") or {}).items()]
    if "screening_plan" in p:
        items = []
        for it in p.get("screening_plan") or []:
            it = dict(it)
            it.setdefault("code", guess_code(it.get("name", "")))
            it.setdefault("related_codes", [it["code"]] if it.get("code") else [])
            items.append(it)
        p["screening_plan"] = items
    return p


# ------------------------------------------------------------------ records + deterministic answers
@dataclass
class PatientAnswer:
    status: str                        # "answered" | "patient_data_unavailable"
    header: str                        # profile id + "synthetic test data" banner
    body: str                          # the patient facts, each line with its [P#] marker
    footer: str                        # fixed safety notes (no interpretation / plan ownership / medication)
    records: list[dict]
    flags: list[str] = field(default_factory=list)
    plan_items: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(x for x in (self.header, self.body, self.footer) if x)


class _Records:
    def __init__(self, profile: dict):
        self.pid = profile.get("patient_id") or "SYN-INLINE"
        self.items: list[dict] = []

    def add(self, kind: str, key: str, text: str, label: str) -> str:
        eid = f"P{len(self.items) + 1}"
        chunk_id = f"{self.pid}::{kind}::{key}"
        for it in self.items:                       # same fact twice -> same marker
            if it["chunk"]["chunk_id"] == chunk_id:
                return it["eid"]
        citation = f"Synthetic patient profile {self.pid} - {label} (synthetic test data)"
        chunk = {"chunk_id": chunk_id, "source_id": f"SYNTHETIC-PATIENT-{self.pid}", "collection": COLLECTION_PATIENT,
                 "title": f"Synthetic patient profile {self.pid}", "version": "synthetic", "section_path": kind,
                 "pdf_page_start": None, "printed_page": "", "url": "", "citation": citation, "text": text}
        self.items.append({"eid": eid, "text": text, "collection": COLLECTION_PATIENT, "citation": citation,
                           "chunk": chunk})
        return eid


def _test_name(code: str | None, lang: str, fallback: str = "") -> str:
    if code in TEST_CATALOG:
        return TEST_CATALOG[code][0 if lang == "en" else 1]
    return fallback or code or ""


def _result_line(r: dict, lang: str) -> str:
    name = r.get("test_ar") if lang == "ar" and r.get("test_ar") else r.get("test") or _test_name(r.get("code"), lang)
    value = r.get("value_ar") if lang == "ar" and r.get("value_ar") else r.get("value")
    unit = f" {r['unit']}" if r.get("unit") else ""
    if r.get("date"):
        when = f" on {r['date']}" if lang == "en" else f" بتاريخ {r['date']}"
    else:
        when = " (date not recorded)" if lang == "en" else " (التاريخ غير مسجّل)"
    return f"{name}: {value}{unit}{when}"


def _result_record_text(r: dict) -> str:
    unit = f" {r['unit']}" if r.get("unit") else ""
    ar = f" | {r['test_ar']}: {r.get('value_ar') or r.get('value')}{unit}" if r.get("test_ar") else ""
    return (f"Previous result: {r.get('test') or r.get('code')} = {r.get('value')}{unit}; date: {r.get('date') or 'not recorded'}; "
            f"source: {r.get('source', 'not recorded')}{ar}")


def _plan_record_text(it: dict) -> str:
    # Bilingual when the profile has Arabic fields, so an Arabic answer citing [P#] can be checked lexically.
    ar = ""
    if it.get("name_ar"):
        ar = f" | {it['name_ar']}" + (f"؛ السبب: {it['reason_ar']}" if it.get("reason_ar") else "")
    return (f"Screening plan item: {it.get('name')}; status: {it.get('status') or 'not recorded'}; due date: "
            f"{it.get('due_date') or 'not recorded'}; last completed: {it.get('last_completed') or 'not recorded'}; "
            f"interval: {it.get('interval') or 'not recorded'}; stored reason: {it.get('reason') or 'none stored'}; "
            f"guideline reference stored with the plan: {it.get('guideline_reference') or 'none stored'}{ar}")


def header(profile: dict, lang: str) -> str:
    pid = profile.get("patient_id") or "inline context"
    label = (profile.get("label_ar") if lang == "ar" else profile.get("label")) or ""
    if lang == "ar":
        return (f"**ملف المريض التجريبي: {pid}{' - ' + label if label else ''}**\n"
                "_بيانات اصطناعية للاختبار فقط، وليست سجلًا لمريض حقيقي._")
    return (f"**Synthetic patient profile: {pid}{' - ' + label if label else ''}**\n"
            "_Synthetic test data only - not a real patient record._")


NO_CONTEXT = {
    "en": ("No synthetic patient profile is selected, so I can't see any personal health data. Select a demo profile "
           "(or send a synthetic patient_context) to ask about personal results or your screening plan, or ask a "
           "general question."),
    "ar": ("لم يتم اختيار ملف مريض تجريبي، لذلك لا أستطيع الاطلاع على أي بيانات صحية شخصية. اختر ملفًا تجريبيًا "
           "(أو أرسل patient_context اصطناعيًا) للسؤال عن نتائجك أو خطة فحوصاتك، أو اسأل سؤالًا عامًا."),
}
NOT_INTERPRETING = {
    "en": "I can't interpret personal results for you; please discuss them with your clinician.",
    "ar": "لا أستطيع تفسير نتائجك الشخصية؛ يرجى مناقشتها مع طبيبك.",
}
PLAN_OWNERSHIP = {
    "en": ("Which screenings apply to you is decided by VITALA's screening plan and your clinician. I can explain the "
           "plan, but I can't add, remove or change recommendations."),
    "ar": ("تحديد الفحوصات المناسبة لك يتم من خلال خطة الفحوصات في VITALA وطبيبك. أستطيع شرح الخطة، لكن لا أستطيع "
           "إضافة توصيات أو حذفها أو تغييرها."),
}


def _missing(lang: str, what: str) -> str:
    return (f"- {what}: not available in this profile. I won't estimate or guess it." if lang == "en"
            else f"- {what}: غير متوفر في هذا الملف. لن أقدّره أو أخمّنه.")


def _latest(results: list[dict]) -> list[dict]:
    dated = [r for r in results if r.get("date")]
    if not dated:
        return results
    last = max(r["date"] for r in dated)
    return [r for r in dated if r["date"] == last]


def _results_for(profile: dict, codes: set[str] | None) -> list[dict]:
    rs = profile.get("previous_results") or []
    return [r for r in rs if codes is None or r.get("code") in codes]


def _plan_for(profile: dict, codes: set[str] | None, statuses: list[str]) -> list[dict]:
    items = profile.get("screening_plan") or []
    if codes:
        items = [it for it in items if it.get("code") in codes or set(it.get("related_codes") or []) & codes]
    if statuses:
        items = [it for it in items if it.get("status") in statuses]
    return items


def answer_patient_question(profile: dict, intent: PatientIntent, lang: str) -> PatientAnswer:
    """Deterministic answer about the selected synthetic profile. Never invents a value."""
    p = normalize_profile(profile)
    rec = _Records(p)
    lines, footer, status, flags, plan_items = [], [], "answered", [], []
    en = lang == "en"
    kind = intent.kind
    codes = expand_codes(intent.codes) if intent.codes else None

    if kind in ("latest_result", "results_history"):
        if "previous_results" not in p:
            lines.append(_missing(lang, "Previous results" if en else "نتائج الفحوصات السابقة"))
            status = "patient_data_unavailable"
        elif intent.codes:
            any_found = False
            for code in intent.codes:
                rs = _results_for(p, expand_codes([code]))
                if not rs:
                    lines.append(_missing(lang, (f"A recorded {_test_name(code, 'en')} result" if en else
                                                 f"نتيجة مسجّلة لـ {_test_name(code, 'ar')}")))
                    continue
                any_found = True
                chosen = sorted(rs, key=lambda r: r.get("date") or "") if kind == "results_history" else _latest(rs)
                for r in chosen:
                    eid = rec.add("result", f"{r.get('code')}::{r.get('date')}::{r.get('test')}", _result_record_text(r),
                                  f"previous result: {r.get('test')}, {r.get('date') or 'date not recorded'}")
                    lines.append(f"- {_result_line(r, lang)} [{eid}]")
            if not any_found:
                status = "patient_data_unavailable"
        else:
            rs = _results_for(p, None)
            if not rs:
                lines.append(_missing(lang, "Previous results" if en else "نتائج الفحوصات السابقة"))
                status = "patient_data_unavailable"
            else:
                chosen = sorted(rs, key=lambda r: r.get("date") or "") if kind == "results_history" else _latest(rs)
                for r in chosen:
                    eid = rec.add("result", f"{r.get('code')}::{r.get('date')}::{r.get('test')}", _result_record_text(r),
                                  f"previous result: {r.get('test')}, {r.get('date') or 'date not recorded'}")
                    lines.append(f"- {_result_line(r, lang)} [{eid}]")
        if status == "answered":
            title = ("Latest recorded result(s):" if kind == "latest_result" else "Recorded results (oldest first):") if en \
                else ("آخر نتيجة مسجّلة:" if kind == "latest_result" else "النتائج المسجّلة (من الأقدم إلى الأحدث):")
            lines.insert(0, title)
            footer.append(NOT_INTERPRETING[lang])

    elif kind in ("plan", "recommendation_reason"):
        if "screening_plan" not in p:
            lines.append(_missing(lang, "Screening plan" if en else "خطة الفحوصات"))
            status = "patient_data_unavailable"
        else:
            items = _plan_for(p, codes, intent.statuses if kind == "plan" else [])
            plan_items = items
            if not items:
                status = "patient_data_unavailable"
                if intent.codes:
                    names = ", ".join(_test_name(c, lang) for c in intent.codes)
                    lines.append(f"This synthetic profile's screening plan does not include {names}." if en else
                                 f"خطة الفحوصات في هذا الملف التجريبي لا تتضمن {names}.")
                elif intent.statuses:
                    sl = ", ".join(STATUS_LABEL[lang][s] for s in intent.statuses)
                    lines.append(f"No screening in this synthetic plan has the status: {sl}." if en else
                                 f"لا يوجد في هذه الخطة التجريبية فحص بالحالة: {sl}.")
                else:
                    lines.append("The screening plan in this synthetic profile is empty." if en else
                                 "خطة الفحوصات في هذا الملف التجريبي فارغة.")
            else:
                lines.append("Your VITALA screening plan (as stored in the profile):" if en else
                             "خطة الفحوصات في VITALA (كما هي مخزّنة في الملف):")
                for it in items:
                    eid = rec.add("plan", it.get("code") or it.get("name"), _plan_record_text(it),
                                  f"screening plan: {it.get('name')}")
                    name = it.get("name_ar") if not en and it.get("name_ar") else it.get("name")
                    st = STATUS_LABEL[lang].get(it.get("status"), it.get("status") or ("not recorded" if en else "غير مسجّلة"))
                    due = it.get("due_date") or ("not recorded" if en else "غير مسجّل")
                    lines.append(f"- **{name}** - {'status' if en else 'الحالة'}: {st}; "
                                 f"{'due date' if en else 'الموعد المقترح'}: {due} [{eid}]")
                    if kind == "recommendation_reason":
                        reason = it.get("reason") if en else (it.get("reason_ar") or it.get("reason"))
                        if reason:
                            lines.append(f"  - {'Reason stored with this recommendation' if en else 'سبب التوصية المخزّن في الخطة'}: "
                                         f"\"{reason}\" [{eid}]")
                        else:
                            lines.append(f"  - {'No reason is stored for this recommendation in the profile.' if en else 'لا يوجد سبب مخزّن لهذه التوصية في الملف.'}")
                            flags.append(f"plan_reason_missing:{it.get('code')}")
                        if it.get("guideline_reference"):
                            lines.append(f"  - {'Guideline reference stored with the plan' if en else 'المرجع المخزّن مع الخطة'}: "
                                         f"{it['guideline_reference']} [{eid}]")
                        related = expand_codes(it.get("related_codes") or [])
                        for r in _latest(_results_for(p, related)) if _results_for(p, related) else []:
                            reid = rec.add("result", f"{r.get('code')}::{r.get('date')}::{r.get('test')}",
                                           _result_record_text(r), f"previous result: {r.get('test')}, {r.get('date')}")
                            lines.append(f"  - {'Latest related result' if en else 'آخر نتيجة مرتبطة'}: "
                                         f"{_result_line(r, lang)} [{reid}]")
            footer.append(PLAN_OWNERSHIP[lang])

    elif kind == "medications":
        if "medications" not in p:
            lines.append(_missing(lang, "Current medications" if en else "الأدوية الحالية"))
            status = "patient_data_unavailable"
        elif not p["medications"]:
            eid = rec.add("medications", "none", "Current medications: none recorded", "current medications")
            lines.append(f"No current medications are recorded in this profile [{eid}]." if en else
                         f"لا توجد أدوية حالية مسجّلة في هذا الملف [{eid}].")
        else:
            lines.append("Current medications recorded in the profile:" if en else "الأدوية الحالية المسجّلة في الملف:")
            for m in p["medications"]:
                txt = " ".join(str(m[k]) for k in ("name", "dose", "frequency") if m.get(k))
                since = f" (since {m['since']})" if m.get("since") else ""
                eid = rec.add("medication", m.get("name", ""), f"Current medication: {txt}{since}", f"medication: {m.get('name')}")
                name = m.get("name_ar") if not en and m.get("name_ar") else m.get("name")
                rest = " ".join(str(m[k]) for k in ("dose", "frequency") if m.get(k))
                lines.append(f"- {name} {rest}{since if en else (' (منذ ' + m['since'] + ')' if m.get('since') else '')} [{eid}]")
            footer.append(("Do not start, stop or change a medication without your doctor or pharmacist." if en else
                                 "لا تبدأ دواء أو توقفه أو تغيّره دون طبيبك أو الصيدلي."))

    elif kind in ("conditions", "family_history", "risk_factors"):
        key = {"conditions": "medical_history", "family_history": "family_history", "risk_factors": "risk_factors"}[kind]
        title = {"conditions": ("Medical history", "التاريخ المرضي"), "family_history": ("Family history", "التاريخ المرضي للعائلة"),
                 "risk_factors": ("Risk factors", "عوامل الخطورة")}[kind][0 if en else 1]
        if key not in p:
            lines.append(_missing(lang, title))
            status = "patient_data_unavailable"
        elif not p[key]:
            eid = rec.add(key, "none", f"{title}: none recorded", title)
            lines.append(f"{title}: none recorded in this profile [{eid}]." if en else f"{title}: لا يوجد شيء مسجّل في هذا الملف [{eid}].")
        else:
            lines.append(f"{title} recorded in the profile:" if en else f"{title} المسجّل في الملف:")
            for x in p[key]:
                main = (x.get("condition_ar") or x.get("factor_ar")) if not en else None
                main = main or x.get("condition") or x.get("factor") or ""
                extra = []
                if x.get("relative"):
                    extra.append(x["relative"])
                if x.get("since"):
                    extra.append(("since " if en else "منذ ") + str(x["since"]))
                if x.get("status"):
                    extra.append(x["status"])
                eid = rec.add(key, main, f"{title}: {x.get('condition') or x.get('factor')} {extra}", title)
                lines.append(f"- {main}{' (' + ', '.join(extra) + ')' if extra else ''} [{eid}]")

    elif kind == "wearable":
        w = p.get("wearable_data")
        if not w:
            lines.append(_missing(lang, "Wearable data (no connected device in this profile)" if en else
                                  "بيانات الأجهزة القابلة للارتداء (لا يوجد جهاز مرتبط في هذا الملف)"))
            status = "patient_data_unavailable"
        else:
            labels = {"avg_daily_steps": ("Average daily steps", "متوسط الخطوات اليومية"),
                      "avg_active_minutes_per_week": ("Active minutes per week", "دقائق النشاط في الأسبوع"),
                      "avg_sleep_hours": ("Average sleep (hours)", "متوسط النوم (ساعات)"),
                      "avg_resting_heart_rate_bpm": ("Average resting heart rate (bpm)", "متوسط نبض القلب أثناء الراحة")}
            txt = "; ".join(f"{k}={w[k]}" for k in labels if w.get(k) is not None)
            eid = rec.add("wearable", w.get("period", ""), f"Wearable data ({w.get('source')}, {w.get('period')}): {txt}",
                          f"wearable data {w.get('period')}")
            lines.append((f"Wearable data from {w.get('source')} for {w.get('period')}:" if en else
                          f"بيانات الأجهزة القابلة للارتداء من {w.get('source')} للفترة {w.get('period')}:"))
            for k, (le, la) in labels.items():
                if w.get(k) is not None:
                    lines.append(f"- {le if en else la}: {w[k]} [{eid}]")

    elif kind == "profile":
        fields = [("age", "Age", "العمر", ""), ("sex", "Sex", "الجنس", ""), ("height_cm", "Height", "الطول", " cm"),
                  ("weight_kg", "Weight", "الوزن", " kg"), ("bmi", "BMI", "مؤشر كتلة الجسم", "")]
        have = [(k, le, la, u) for k, le, la, u in fields if p.get(k) is not None]
        if not have:
            lines.append(_missing(lang, "Basic profile information" if en else "المعلومات الأساسية"))
            status = "patient_data_unavailable"
        else:
            txt = "; ".join(f"{k}={p[k]}" for k, *_ in have)
            eid = rec.add("profile", "basics", f"Basic information: {txt}", "basic information")
            for k, le, la, u in have:
                lines.append(f"- {le if en else la}: {p[k]}{u} [{eid}]")
            for k, le, la, _ in fields:
                if p.get(k) is None:
                    lines.append(_missing(lang, le if en else la))

    return PatientAnswer(status, header(p, lang), "\n".join(lines), "\n".join(footer), rec.items, flags, plan_items)
