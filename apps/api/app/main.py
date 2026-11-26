from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.errores import registrar_manejadores
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.observabilidad import iniciar_sentry
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = Redis.from_url(settings.redis_url)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


_is_prod = settings.environment == "production"
iniciar_sentry("api")

app = FastAPI(
    title="PH-SaaS API",
    version="1.0.0",
    lifespan=lifespan,
    # La documentación interactiva expone el mapa completo de la API: solo fuera de producción
    docs_url=None if _is_prod else "/docs",
    redoc_url=None,
    openapi_url=None if _is_prod else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

registrar_manejadores(app)
app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness: el proceso responde."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["system"])
async def ready(response: Response) -> dict[str, str]:
    """Readiness: dependencias críticas disponibles."""
    checks: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc.__class__.__name__}"
    try:
        await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}"

    if any(v != "ok" for v in checks.values()):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return checks
