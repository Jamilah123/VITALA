"""VITALA chatbot endpoints. The answers come from the RAG service in rag/.

The chatbot explains evidence and existing draft screening output. It never
decides eligibility, creates a schedule, or interprets a personal result.
Patient data is sent only for synthetic demo patients and only on an explicit
request; insurance details and identifiers are never sent.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import select

from app.chat_context import PatientContextNotAllowed, build_patient_context, require_synthetic
from app.database import SessionDep
from app.medical_history import patient_risk_context
from app.models import MedicationUse, Patient, ScreeningRecord
from app.rag_client import RagUnavailable
from app.routers.profiles import get_patient_or_404
from app.routers.screening_records import get_record_or_404, list_records
from app.schemas import (
    AnalyzedResult,
    ChatCitation,
    ChatPatientContextInfo,
    ChatReply,
    ChatRequest,
    ChatStatus,
    ResultAnalysisRead,
    ResultAnalysisRequest,
)
from app.screening import summarize_screening

router = APIRouter(tags=["Chatbot"])

UNAVAILABLE = {"code": "chat_unavailable", "message": "The VITALA assistant is not available right now. Please try again later."}
NOT_SYNTHETIC = {
    "code": "patient_context_disabled",
    "message": "Personal data can be used by the assistant only for synthetic demo patients until authentication and privacy approval exist.",
}

QUESTION_TEMPLATE = {
    "en": "What does my latest {test} result mean?",
    "ar": "وش معنى آخر نتيجة {test} عندي؟",
}
LIMITATIONS = {
    "not_interpreted": {
        "en": "VITALA does not interpret your personal result or diagnose. Please discuss it with your clinician.",
        "ar": "لا يفسّر VITALA نتيجتك الشخصية ولا يشخّص. يرجى مناقشتها مع طبيبك.",
    },
    "general_sources": {
        "en": "The explanation uses general reference sources that have not been clinically reviewed for VITALA.",
        "ar": "يعتمد الشرح على مصادر مرجعية عامة لم تتم مراجعتها سريريًا لتطبيق VITALA.",
    },
    "reference_range": {
        "en": "The laboratory reference range was not recorded, so none is shown or estimated.",
        "ar": "لم يُسجَّل المدى المرجعي للمختبر، لذلك لا يُعرض ولا يُقدَّر.",
    },
    "unit": {
        "en": "No unit was recorded with this result.",
        "ar": "لم تُسجَّل وحدة القياس مع هذه النتيجة.",
    },
}


def _rag(request: Request):
    return request.app.state.rag_client


def chat_reply(raw: dict, context: ChatPatientContextInfo) -> ChatReply:
    view = raw.get("patient_view") or {}
    return ChatReply(
        request_id=str(raw.get("request_id", "")),
        status=str(raw.get("status", "error")),
        language=str(raw.get("language", "ar")),
        answer=str(raw.get("answer", "")),
        display_text=str(view.get("text") or raw.get("answer", "")),
        notices=[str(item) for item in view.get("notices", [])],
        citations=[
            ChatCitation(
                evidence_id=str(item.get("evidence_id", "")),
                source_id=str(item.get("source_id", "")),
                collection=str(item.get("collection", "")),
                title=str(item.get("title", "")),
                citation=str(item.get("citation", "")),
                url=str(item.get("url") or ""),
                pdf_page=item.get("pdf_page"),
            )
            for item in raw.get("citations", [])
        ],
        safety_flags=[str(flag) for flag in raw.get("safety_flags", [])],
        route=str(raw.get("route", "")),
        disclaimer=str(raw.get("disclaimer", "")),
        llm_provider=str(raw.get("llm_provider", "")),
        patient_context=context,
    )


def _ask(request: Request, question: str, context: dict | None) -> dict:
    try:
        return _rag(request).chat(question, context)
    except RagUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=UNAVAILABLE)


def _synthetic_patient(session, patient_id: int) -> Patient:
    patient = get_patient_or_404(session, patient_id)
    try:
        require_synthetic(patient)
    except PatientContextNotAllowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOT_SYNTHETIC)
    return patient


@router.get("/chat/status", response_model=ChatStatus, description="Whether the RAG service is reachable. Never returns an answer.")
def chat_status(request: Request) -> ChatStatus:
    try:
        health = _rag(request).health()
    except RagUnavailable as exc:
        return ChatStatus(available=False, reason=str(exc))
    return ChatStatus(available=True, llm_provider=health.get("llm_provider"), pipeline_version=health.get("pipeline_version"))


@router.post(
    "/chat",
    response_model=ChatReply,
    description=(
        "Ask the VITALA assistant. Without patient_id the question is answered from general knowledge only. "
        "With patient_id, that patient's records are sent as context, which is allowed only for synthetic demo patients (403 otherwise). "
        "503 when the assistant is not running."
    ),
)
def chat(body: ChatRequest, request: Request, session: SessionDep) -> ChatReply:
    if body.patient_id is None:
        return chat_reply(_ask(request, body.question, None), ChatPatientContextInfo(used=False, synthetic=False))

    patient = _synthetic_patient(session, body.patient_id)
    rule_set = request.app.state.rule_set
    uses = session.exec(select(MedicationUse).where(MedicationUse.patient_id == patient.id)).all()
    risk = patient_risk_context(session, patient.id, rule_set)
    summary = summarize_screening(rule_set, patient, uses, list_records(session, patient.id), date.today(), risk=risk)
    context, sections = build_patient_context(session, patient, rule_set, request.app.state.catalogue, date.today(), summary=summary)
    info = ChatPatientContextInfo(used=True, synthetic=True, patient_id=patient.id, fields_sent=sections)
    return chat_reply(_ask(request, body.question, context), info)


@router.post(
    "/patients/{patient_id}/screening-records/{record_id}/analysis",
    response_model=ResultAnalysisRead,
    tags=["Screening history"],
    description=(
        "Analyze with VITALA: explain one stored result in plain language. Sends only this result and basic synthetic "
        "context. Synthetic demo patients only (403 otherwise); 422 if the record has no result value; 503 if the assistant is down."
    ),
)
def analyze_record(patient_id: int, record_id: int, body: ResultAnalysisRequest, request: Request, session: SessionDep) -> ResultAnalysisRead:
    patient = _synthetic_patient(session, patient_id)
    record: ScreeningRecord = get_record_or_404(session, patient_id, record_id)
    missing = [name for name in ("result", "unit", "reference_range") if not getattr(record, name)]
    if record.result is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["path", "record_id"], "msg": "This record has no result value to explain", "type": "value_error"}],
        )

    lang = body.language
    context, sections = build_patient_context(
        session, patient, request.app.state.rule_set, request.app.state.catalogue, date.today(), only_record=record
    )
    question = QUESTION_TEMPLATE[lang].format(test=record.test_name)
    raw = _ask(request, question, context)
    limitations = [LIMITATIONS["not_interpreted"][lang], LIMITATIONS["general_sources"][lang]]
    limitations += [LIMITATIONS[name][lang] for name in ("reference_range", "unit") if name in missing]
    return ResultAnalysisRead(
        result=AnalyzedResult(
            record_id=record.id,
            test_id=record.test_id,
            test_name=record.test_name,
            result=record.result,
            unit=record.unit,
            completed_on=record.completed_on,
            reference_range=record.reference_range,
            source=record.source,
            missing_fields=missing,
        ),
        explanation=chat_reply(raw, ChatPatientContextInfo(used=True, synthetic=True, patient_id=patient.id, fields_sent=sections)),
        limitations=limitations,
    )
