from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from api.routers import auth, health, internal, runner, webhooks
from api.routers.admin import router as admin_router
from core.config import settings
from core.logging import configure_logging
from core.middleware import RequestContextMiddleware
from database.seed import seed_reference_data
from database.session import dispose_engine, session_scope
from services.errors import ConflictError, DomainError, NotFoundError

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production_secrets()
    async with session_scope() as session:
        await seed_reference_data(session)
    yield
    await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    status_code = 400
    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, ConflictError):
        status_code = 409
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, __: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "数据已存在或与现有记录冲突", "code": "INTEGRITY_ERROR"},
    )


app.include_router(health.router)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(internal.router, prefix=settings.api_prefix)
app.include_router(webhooks.router, prefix=settings.api_prefix)
app.include_router(runner.router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "docs": "/docs"}
