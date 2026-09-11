import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.videos import router as videos_router
from core.config import settings
from core.rate_limit import limiter
from database.session import init_db

# --- Logging: respect LOG_LEVEL, append instead of overwrite ---
log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug.log")
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Suppress noisy third-party loggers
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database on startup. Never crash boot: if the DB is
    # unreachable (bad credentials, network), log loudly and keep serving
    # /health + /api/settings so the problem is diagnosable. DB endpoints
    # return 503 until init succeeds.
    try:
        await init_db()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Database init failed — API running in degraded mode (DB endpoints 503). "
            "Check DATABASE_URL. Error: %s",
            exc,
        )
    # Warm up IndoBERT in background so first job is fast (non-blocking).
    try:
        import asyncio

        from services.nlp import IndoBERTService

        def _warmup() -> None:
            try:
                IndoBERTService().load_indobert()
            except Exception as exc:  # noqa: BLE001 - warmup must never crash boot
                logger.warning("IndoBERT warmup failed: %s", exc)

        asyncio.get_running_loop().run_in_executor(None, _warmup)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Warmup scheduling failed: %s", exc)
    yield


app = FastAPI(title="Echolens API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(videos_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Admin-Token"],
    max_age=3600,
)
# Prevent Host header attacks; allow localhost + configured origins' hosts.
_allowed_hosts = {"localhost", "127.0.0.1", "testserver"}
for _origin in settings.cors_origin_list():
    try:
        from urllib.parse import urlparse as _urlparse

        _host = _urlparse(_origin).hostname
        if _host:
            _allowed_hosts.add(_host)
    except Exception:  # noqa: BLE001
        continue
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(_allowed_hosts))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Minimal hardening headers; CSP is page-level (frontend has no inline scripts).
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500, content={"detail": "Internal server error."}
    )


@app.get("/health")
async def health_check():
    from database.session import DB_BACKEND, DB_ERROR, DB_READY

    return {
        "status": "ok" if DB_READY else "degraded",
        "db_ready": DB_READY,
        "db_backend": DB_BACKEND,
        "db_error": DB_ERROR if not DB_READY else "",
        "gemini_enabled": bool(settings.GEMINI_API_KEY.strip()),
        "env": settings.APP_ENV,
        "limits": {
            "max_process_limit": settings.MAX_PROCESS_LIMIT,
            "max_comment_page_size": settings.MAX_COMMENT_PAGE_SIZE,
            "max_chat_context": settings.MAX_CHAT_CONTEXT,
            "max_question_length": settings.MAX_QUESTION_LENGTH,
            "chat_context_fraction": settings.CHAT_CONTEXT_FRACTION,
            "chat_context_min": settings.CHAT_CONTEXT_MIN,
        },
    }


@app.get("/api/settings")
async def public_settings():
    """Non-secret runtime caps so the frontend settings UI can clamp inputs."""
    return {
        "gemini_enabled": bool(settings.GEMINI_API_KEY.strip()),
        "max_process_limit": settings.MAX_PROCESS_LIMIT,
        "max_comment_page_size": settings.MAX_COMMENT_PAGE_SIZE,
        "max_chat_context": settings.MAX_CHAT_CONTEXT,
        "max_question_length": settings.MAX_QUESTION_LENGTH,
        "chat_context_fraction": settings.CHAT_CONTEXT_FRACTION,
        "chat_context_min": settings.CHAT_CONTEXT_MIN,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.APP_ENV == "development",
    )
