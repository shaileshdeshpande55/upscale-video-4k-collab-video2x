"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Callable

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import make_auth
from app.config import Settings, load_settings
from app.routes.files import router as files_router
from app.routes.jobs import router as jobs_router
from app.routes.system import router as system_router


def create_app(settings: Settings | None = None, job_manager_factory: Callable | None = None) -> FastAPI:
    settings = settings or load_settings()
    auth = make_auth(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.job_manager = None
        if job_manager_factory is not None:
            app.state.job_manager = job_manager_factory(settings)
        yield
        if app.state.job_manager is not None and hasattr(app.state.job_manager, "shutdown"):
            app.state.job_manager.shutdown()

    app = FastAPI(title="Video2X Colab Backend", lifespan=lifespan)
    app.state.settings = settings
    app.state.job_manager = None

    origins = settings.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    # Apply auth to all /api routes
    app.include_router(system_router, dependencies=[Depends(auth)])
    app.include_router(jobs_router, dependencies=[Depends(auth)])
    app.include_router(files_router, dependencies=[Depends(auth)])

    @app.exception_handler(Exception)
    async def unhandled(request, exc):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    return app
