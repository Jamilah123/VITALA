"""Deterministic safety rules that run BEFORE retrieval and generation.

These rules are intentionally simple, explicit and testable. They are not a clinical triage tool:
the keyword lists and the escalation wording MUST be reviewed by the VITALA medical team.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .retrieval import normalize_arabic

# ------------------------------------------------------------------ emergencies
EMERGENCY_EN = [
    r"chest (pain|tightness|pressure)", r"(can'?t|cannot|unable to|hard to|trouble|difficulty) breath",
    r"short(ness)? of breath", r"\bfaint(ed|ing)?\b", r"passed out", r"unconscious", r"not waking up",
    r"(face|mouth) (is )?droop", r"slurred speech", r"(weak|numb)(ness)? (on|in) one side", r"sudden (weakness|numbness|confusion|vision loss)",
    r"\bstroke\b.*(now|happening|having)", r"(having|think i.?m having) a (heart attack|stroke)", r"heart attack",
    r"seizure", r"convuls", r"severe bleeding", r"vomiting blood", r"coughing (up )?blood",
    r"suicid", r"kill myself", r"end my life", r"self[- ]harm", r"want to die",
    r"(swollen|swelling of) (my )?(face|lips|tongue|throat)", r"anaphyla", r"overdos", r"took too many",
    r"(very|extremely|really) (low|high) (blood )?sugar.*(confus|faint|sweat|shak|vomit)",
    r"worst headache", r"severe (headache|abdominal pain|chest pain)",
    # Angioedema (ACE inhibitors): swelling of the lips / tongue / face / throat reported now.
    r"\b(lips?|tongue|face|throat|mouth) (is |are |has |have )?(started )?(swelling|swollen|swelled)",
    r"throat (is |feels )?(closing|tight)", r"(can'?t|cannot|hard to) swallow",
]
EMERGENCY_AR = [
    "الم في الصدر", "الم بالصدر", "ألم في الصدر", "ألم بالصدر", "ضيق في الصدر", "ضيق تنفس", "ضيق في التنفس", "صعوبه في التنفس",
    "صعوبة في التنفس", "ما اقدر اتنفس", "لا استطيع التنفس", "اغماء", "إغماء", "اغمي علي", "فقدان الوعي", "فقد الوعي",
    "جلطه", "جلطة", "سكته", "سكتة", "تنميل في جهه", "تنميل في جهة", "شلل", "ثقل في اللسان", "ميلان الوجه", "تشنج", "نوبه صرع",
    "نزيف شديد", "استفراغ دم", "انتحار", "انتحر", "اقتل نفسي", "اذيه نفسي", "إيذاء نفسي", "ابي اموت", "اريد ان اموت",
    "تورم الوجه", "تورم الحلق", "تورم اللسان", "جرعه زائده", "جرعة زائدة", "بلعت حبوب كثير", "اخذت حبوب كثير",
    "صداع شديد جدا", "اسوا صداع",
    # Angioedema (ACE inhibitors), Saudi dialect and MSA
    "شفايفي متورمه", "شفايفي منتفخه", "لساني متورم", "لساني منتفخ", "وجهي متورم", "وجهي منتفخ", "حلقي متورم",
    "تورم في الشفايف", "تورم في الشفاه", "تورم في اللسان", "تورم في الحلق", "انتفاخ الشفايف", "انتفاخ الوجه",
    "انتفاخ اللسان", "ما اقدر ابلع", "صعوبه في البلع", "صعوبة في البلع",
]
_EMERGENCY_AR_N = [normalize_arabic(x) for x in EMERGENCY_AR]
# Allow intervening adjectives, e.g. "ضيق شديد في التنفس" and "ألم قوي في الصدر".
# This is a limited prototype safety net, NOT validated clinical triage.
EMERGENCY_AR_PATTERNS = [
    r"ضيق(?:\s+[\u0621-\u064a]+){0,2}\s+(?:في\s+|ب)?التنفس",
    r"صعوبه(?:\s+[\u0621-\u064a]+){0,2}\s+(?:في\s+|ب)?التنفس",
    r"(?:الم|وجع)(?:\s+[\u0621-\u064a]+){0,2}\s+(?:في\s+|ب)?الصدر",
]
BP_RE = re.compile(r"(\d{2,3})\s*/\s*(\d{2,3})")
# Always escalate, whatever the phrasing
ALWAYS_EMERGENCY_EN = [r"suicid", r"kill myself", r"end my life", r"self[- ]harm", r"want to die", r"overdos", r"took too many"]
ALWAYS_EMERGENCY_AR = [normalize_arabic(x) for x in ["انتحار", "انتحر", "اقتل نفسي", "اذيه نفسي", "إيذاء نفسي", "ابي اموت",
                                                      "اريد ان اموت", "جرعة زائدة", "جرعه زائده", "بلعت حبوب كثير", "اخذت حبوب كثير"]]
# "Can lisinopril cause swelling of the lips?" is a general medication question, not an emergency report.
GENERAL_FRAMING_RE = re.compile(
    r"\b(can|does|do|could|may|will|is|are)\b.{0,60}\b(cause|causes|lead to|increase|reduce|lower|prevent|symptom|sign|side effect)|"
    r"\brisk of\b|\bside effects?\b|\bwhat (is|are)\b|\bdefinition\b|\bwarning signs?\b|"
    r"(هل يسبب|هل تسبب|يقلل|يزيد خطر|خطر|ما هو|ما هي|اعراض جانبيه|علامات)", re.I)
PERSONAL_CUE_RE = re.compile(
    r"\b(i|i'm|im|i am|i've|ive|my|me|we|he|she|someone|right now|now|currently|today|tonight)\b|"
    r"(عندي|احس|أحس|اشعر|أشعر|اعاني|أعاني|معي|الحين|الان|الآن|ابوي|أبوي|امي|أمي|زوجي|زوجتي|ولدي|بنتي|صار لي|جاني)", re.I)

EMERGENCY_MESSAGE = {
    "en": ("This may be a medical emergency. Please do not wait for an app answer: call the Saudi Red Crescent "
           "ambulance on 997 (or the unified emergency number 911 where available) or go to the nearest emergency "
           "department now. If someone is with you, ask them to help. VITALA's assistant cannot assess emergencies."),
    "ar": ("قد تكون هذه حالة طبية طارئة. لا تنتظر إجابة من التطبيق: اتصل بالإسعاف (الهلال الأحمر السعودي) على 997 "
           "(أو رقم الطوارئ الموحد 911 حيث يتوفر) أو توجّه فورًا إلى أقرب قسم طوارئ. إذا كان معك أحد فاطلب مساعدته. "
           "مساعد VITALA لا يستطيع تقييم الحالات الطارئة."),
}

# ------------------------------------------------------------------ personal advice
PERSONAL_DOSING = [
    r"\b(should|can|may) i (stop|quit|skip|double|increase|decrease|reduce|lower|raise|change|switch|start)\b",
    r"\b(increase|decrease|reduce|double|change|adjust) (my|the) (dose|dosage|medication|pills?|tablets?)",
    r"how (much|many) (mg|milligrams?|pills?|tablets?)? ?(of \w+ )?should i (take|use)",
    r"what dose should i", r"\bmy dose\b", r"stop taking my", r"instead of my",
    r"\b(which|what) dose\b.{0,40}\b(take|use|start|give)\b", r"\b(max(imum)?|highest|safe|right|correct) dose\b.{0,60}\b(i|me)\b", r"\bhow (much|many)\b.{0,50}\bcan i (take|have|use)\b", r"\bhow (much|many) .{0,30}\bshould (i|he|she|we) take\b",
]
PERSONAL_DOSING_AR = ["اوقف الدواء", "أوقف الدواء", "اوقف العلاج", "اترك الدواء", "اوقف حبوب", "ازيد الجرعه", "أزيد الجرعة",
                      "انقص الجرعه", "اقلل الجرعه", "اضاعف الجرعه", "كم حبه اخذ", "كم حبة آخذ", "كم جرعه اخذ", "كم ملغ اخذ",
                      "هل اوقف", "هل أوقف", "هل اترك", "هل ازيد", "هل اقلل", "هل اغير الدواء", "اغير جرعتي"]
_DOSING_AR_N = [normalize_arabic(x) for x in PERSONAL_DOSING_AR]

DIAGNOSIS = [r"\bdo i have\b", r"\bam i (diabetic|hypertensive|sick)\b", r"diagnose me", r"\bwhat (disease|condition) do i have\b",
             r"\bis (it|this) (cancer|diabetes)\b"]
DIAGNOSIS_AR = ["هل عندي", "هل انا مصاب", "هل أنا مصاب", "شخصني", "وش مرضي", "ما هو مرضي", "هل هذا سرطان"]
_DIAG_AR_N = [normalize_arabic(x) for x in DIAGNOSIS_AR]

ELIGIBILITY = [r"\bam i eligible\b", r"\bdo i need (a|an|to)?\s*\w*\s*(screen|test|check)", r"\bshould i (get|have|do) (a|an)?\s*\w*\s*(screen|test|mammo|colonoscopy)"]
ELIGIBILITY_AR = ["هل احتاج فحص", "هل أحتاج فحص", "هل لازم اسوي فحص", "هل يجب ان اعمل فحص", "هل انا مؤهل"]
_ELIG_AR_N = [normalize_arabic(x) for x in ELIGIBILITY_AR]

INJECTION = [r"ignore (all |the |your |my )?(previous|prior|above|earlier) (instructions|rules|prompts?)", r"ignore (all )?(your|the) (rules|instructions|guidelines)", r"system prompt", r"you are now",
             r"developer mode", r"jailbreak", r"disregard (your|the) (rules|guidelines)", r"pretend (to be|you are)",
             r"act as (a|my) doctor", r"تجاهل التعليمات", "انس التعليمات"]

DECLINE_DOSING = {
    "en": ("I can't advise you to start, stop or change a medication or its dose. Those decisions depend on your full "
           "medical history and must be made with your doctor or pharmacist. I can explain what the reference sources "
           "say about a medication in general if that helps."),
    "ar": ("لا أستطيع أن أنصحك ببدء دواء أو إيقافه أو تغيير جرعته. هذه القرارات تعتمد على تاريخك الطبي الكامل ويجب أن "
           "تُتخذ مع طبيبك أو الصيدلي. يمكنني أن أشرح ما تذكره المراجع الطبية عن الدواء بشكل عام إذا كان ذلك مفيدًا."),
}
DECLINE_OTHER_DRUG = {
    "en": ("This demo of the VITALA assistant only covers metformin and the ACE inhibitor medicines (for example "
           "lisinopril, enalapril, ramipril, captopril and perindopril). Please ask your pharmacist or doctor about "
           "other medications."),
    "ar": ("هذه النسخة التجريبية من مساعد VITALA تغطي فقط الميتفورمين وأدوية مثبطات الإنزيم المحول للأنجيوتنسين "
           "(مثل الليسينوبريل والإنالابريل والراميبريل والكابتوبريل والبيريندوبريل). يرجى سؤال الصيدلي أو الطبيب عن "
           "الأدوية الأخرى."),
}
INSUFFICIENT = {
    "en": ("I couldn't find enough information in VITALA's approved reference sources to answer this reliably, "
           "so I won't guess. Please ask your doctor, or rephrase the question about preventive screening, diabetes, "
           "high blood pressure, metformin or ACE inhibitor medicines."),
    "ar": ("لم أجد معلومات كافية في المصادر المعتمدة لدى VITALA للإجابة عن هذا السؤال بشكل موثوق، لذلك لن أخمّن. "
           "يرجى استشارة طبيبك، أو إعادة صياغة السؤال حول الفحوصات الوقائية أو السكري أو ضغط الدم أو الميتفورمين "
           "أو أدوية مثبطات الإنزيم المحول للأنجيوتنسين."),
}
DISCLAIMER = {
    "en": "General information from reference documents, not a diagnosis or personal medical advice.",
    "ar": "معلومات عامة من مراجع معتمدة، وليست تشخيصًا أو نصيحة طبية شخصية.",
}


@dataclass
class SafetyResult:
    emergency: bool = False
    flags: list[str] = field(default_factory=list)
    reason: str = ""


def _any(patterns, text):
    return any(re.search(p, text, re.I) for p in patterns)


def check_question(question: str) -> SafetyResult:
    q = question.strip()
    qn = normalize_arabic(q.lower())
    res = SafetyResult()
    always = _any(ALWAYS_EMERGENCY_EN, q) or any(p in qn for p in ALWAYS_EMERGENCY_AR)
    symptom = (_any(EMERGENCY_EN, q) or any(p in qn for p in _EMERGENCY_AR_N)
               or _any(EMERGENCY_AR_PATTERNS, qn))
    personal = bool(PERSONAL_CUE_RE.search(q) or PERSONAL_CUE_RE.search(qn))
    general = bool(GENERAL_FRAMING_RE.search(q) or GENERAL_FRAMING_RE.search(qn))
    if always or (symptom and (personal or not general)):
        res.emergency, res.reason = True, "emergency_keywords"
        res.flags.append("emergency_symptoms")
    elif symptom:
        res.flags.append("emergency_topic_general_question")
    for m in BP_RE.finditer(normalize_arabic(q)):
        sbp, dbp = int(m.group(1)), int(m.group(2))
        if 60 <= dbp < sbp <= 300 and (sbp >= 180 or dbp >= 120):
            res.emergency, res.reason = True, f"severe_bp_reading_{sbp}/{dbp}"
            res.flags.append("severe_blood_pressure_reading")
    if _any(PERSONAL_DOSING, q) or any(p in qn for p in _DOSING_AR_N):
        res.flags.append("personal_dosing_request")
    if _any(DIAGNOSIS, q) or any(p in qn for p in _DIAG_AR_N):
        res.flags.append("diagnosis_request")
    if _any(ELIGIBILITY, q) or any(p in qn for p in _ELIG_AR_N):
        res.flags.append("eligibility_question")
    if _any(INJECTION, q):
        res.flags.append("prompt_injection_attempt")
    return res


# ------------------------------------------------------------------ retrieved text hygiene
EVIDENCE_INJECTION_RE = re.compile(
    r"(ignore (all |the )?(previous|prior|above) instructions|you are (now )?an? (ai|assistant)|system prompt|"
    r"<\s*/?\s*(system|instructions?|evidence)\s*>)", re.I)


def sanitize_evidence(text: str) -> tuple[str, bool]:
    """Neutralise anything in a retrieved chunk that looks like markup or instructions to the model.

    The source documents are trusted publishers, but extraction errors or a tampered file could still
    inject text, so retrieved content is always treated as data.
    """
    flagged = bool(EVIDENCE_INJECTION_RE.search(text))
    text = EVIDENCE_INJECTION_RE.sub("[removed]", text)
    text = text.replace("<", "‹").replace(">", "›") if "<" in text and re.search(r"<\s*/?\s*[a-zA-Z]", text) else text
    return text, flagged


APP_ACTION_DISCLAIMER = {
    "en": ("I can't book, change or cancel appointments, upload results or change anything in the VITALA app myself. "
           "Here is how the app documentation describes doing it:"),
    "ar": ("لا أستطيع حجز المواعيد أو تعديلها أو إلغاؤها أو رفع النتائج أو تغيير أي شيء في تطبيق VITALA بنفسي. "
           "هذه هي الخطوات كما تصفها وثائق التطبيق:"),
}
INSUFFICIENT_APP = {
    "en": ("I couldn't find this in VITALA's app documentation, so I won't guess how the app handles it. "
           "Please check the app itself or contact VITALA support."),
    "ar": ("لم أجد هذه المعلومة في وثائق تطبيق VITALA، لذلك لن أخمّن طريقة عمل التطبيق فيها. "
           "يرجى مراجعة التطبيق نفسه أو التواصل مع دعم VITALA."),
}

# Legacy fields (first prototype) + the full profile schema (patient_context.py). Anything else is dropped.
PATIENT_CONTEXT_FIELDS = {
    "is_synthetic", "age", "sex", "bmi", "conditions", "medications", "risk_factors", "screening_plan", "recent_results",
    "patient_id", "label", "label_ar", "height_cm", "weight_kg", "medical_history", "family_history",
    "previous_results", "wearable_data", "data_as_of",
}
SYNTHETIC_ID_RE = re.compile(r"^SYN-[A-Z0-9-]{1,32}$")


def sanitize_patient_context(ctx: dict | None) -> tuple[dict | None, list[str]]:
    """Keep only expected fields; reject contexts not marked synthetic (prototype must not process real PHI)."""
    if not ctx:
        return None, []
    flags = []
    if ctx.get("is_synthetic") is not True:
        return None, ["patient_context_rejected_not_marked_synthetic"]
    allowed = PATIENT_CONTEXT_FIELDS
    # None means "not provided" (reported as unavailable), except wearable_data where None means "no device".
    clean = {k: v for k, v in ctx.items() if k in allowed and (v is not None or k == "wearable_data")}
    dropped = set(ctx) - allowed
    if dropped:
        flags.append("patient_context_fields_dropped:" + ",".join(sorted(dropped)))
    # An identifier that does not look synthetic could be a real record number: never keep or echo it.
    if "patient_id" in clean and not SYNTHETIC_ID_RE.match(str(clean["patient_id"])):
        clean.pop("patient_id")
        flags.append("patient_id_dropped_not_synthetic_format")
    import json
    s = json.dumps(clean, ensure_ascii=False)
    if _any(INJECTION, s):
        flags.append("prompt_injection_in_patient_context")
        return None, flags
    return clean, flags
