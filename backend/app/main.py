from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.catalogue import load_catalogue
from app.config import Settings
from app.database import SessionDep, build_engine, init_db
from app.routers import medications, profiles
from app.schemas import HealthRead


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Creates missing tables only. Seeding is the explicit app.seed command.
        init_db(engine, settings.database_path)
        yield
        engine.dispose()

    app = FastAPI(
        title="VITALA API",
        version="0.1.0",
        description="Milestone one, for local use with synthetic data only. No authentication yet.",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.catalogue = load_catalogue(settings.medications_path)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
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
    return app


app = create_app()
