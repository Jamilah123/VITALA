from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.catalogue import load_catalogue
from app.config import Settings
from app.criteria import check_criteria_cover
from app.crypto import FieldCipher
from app.database import SessionDep, build_engine, init_db
from app.history_mappings import check_history_mappings
from app.proposals import load_proposals
from app.rag_client import RagClient
from app.routers import (
    chat,
    clinics,
    insurance,
    medical_history,
    medications,
    profiles,
    risk_profiles,
    screening,
    screening_records,
)
from app.rules import load_rule_set
from app.schemas import HealthRead
from app.screening_tests import check_test_mapping
from app.virtual_care import NoVirtualCareProvider

# Values of these fields must never be echoed back in an error response.
SENSITIVE_FIELDS = frozenset({"national_id", "member_number"})


def _redacted(errors: list[dict], path: str) -> list[dict]:
    clean = []
    for error in errors:
        error = dict(error)
        if "/insurance" in path or SENSITIVE_FIELDS & {str(part) for part in error.get("loc", ())}:
            error.pop("input", None)
            error.pop("ctx", None)
        clean.append(error)
    return clean


def create_app(settings: Settings | None = None, rag_client: RagClient | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Creates missing tables and applies additive migrations. Seeding is the explicit app.seed command.
        init_db(engine, settings.database_path, settings.backup_dir)
        yield
        engine.dispose()
        _app.state.rag_client.close()

    app = FastAPI(
        title="VITALA API",
        version="0.2.0",
        description=(
            "For local use with synthetic data only. No authentication yet. "
            "Screening output comes from draft rules no clinician has approved; nothing is scheduled."
        ),
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.catalogue = load_catalogue(settings.medications_path)
    app.state.rule_set = load_rule_set(app.state.catalogue)
    check_criteria_cover(app.state.rule_set.rules)
    check_test_mapping(app.state.rule_set.rules)
    check_history_mappings(app.state.rule_set.rules)
    app.state.proposals = load_proposals(app.state.rule_set, app.state.catalogue)
    key = settings.field_encryption_key.get_secret_value() if settings.field_encryption_key else None
    app.state.field_cipher = FieldCipher(key)
    app.state.rag_client = rag_client or RagClient(settings.rag_url, settings.rag_timeout_seconds)
    app.state.virtual_care = NoVirtualCareProvider()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": jsonable_encoder(_redacted(list(exc.errors()), request.url.path))},
        )

    @app.get("/health", response_model=HealthRead, tags=["Health"])
    def health(session: SessionDep, response: Response) -> HealthRead:
        try:
            session.exec(select(1)).one()
        except SQLAlchemyError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthRead(status="unavailable", database="unreachable")
        return HealthRead(status="ok", database="ok")

    app.include_router(profiles.router)
    app.include_router(medications.router)
    app.include_router(risk_profiles.router)
    app.include_router(medical_history.router)
    app.include_router(insurance.router)
    app.include_router(clinics.router)
    app.include_router(screening.router)
    app.include_router(screening_records.router)
    app.include_router(chat.router)
    return app


app = create_app()
