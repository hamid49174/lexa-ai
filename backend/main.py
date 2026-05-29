"""Lexa AI — FastAPI Backend v1.0.0
Hauptserver auf localhost:8000
Production-grade: Request-ID Middleware, Body Size Limits, Response Caching,
Consistent Error Handling, Parallelized Startup, Robust Exception Guards
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from backend.config import VERSION as APP_VERSION

# ── Sentry Error Tracking (must init before FastAPI) ──────
_sentry_available = False
_sentry_dsn = ""
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    _sentry_available = True
except ImportError:
    print("[Main] sentry-sdk not installed — error tracking disabled")

if _sentry_available:
    _sentry_dsn = os.environ.get("SENTRY_DSN", "")
    if not _sentry_dsn:
        try:
            import keyring
            _sentry_dsn = keyring.get_password("lexa-ai", "sentry_dsn") or ""
        except Exception:
            pass

    if _sentry_dsn:
        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
            ],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=os.environ.get("LEXA_ENV", "production"),
            release=f"lexa-ai@{os.environ.get('LEXA_VERSION', APP_VERSION)}",
            send_default_pii=False,
        )

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from backend.config import (
    VERSION,
    BACKEND_HOST,
    BACKEND_PORT,
    MAX_BODY_SIZE,
    MAX_HISTORY,
    CACHE_HEALTH_TTL,
    SLOW_REQUEST_THRESHOLD,
)
from backend.error_response import error_payload
from backend.local_auth import (
    LOCAL_AUTH_HEADER,
    health_auth_fields,
    is_local_auth_required,
    is_public_path as is_local_auth_public_path,
    request_has_valid_local_token,
)
from backend.shared import (
    conversation_history,
    _history_lock,
    cache_get,
    cache_set,
)
from backend.ai_engine import (
    get_ai_models,
    get_ai_status,
    set_ai_model as set_active_ai_model,
    generate_title,
)
from backend.hermes_adapter import get_hermes_status
from backend import memory
from backend.scheduler import start_scheduler, get_scheduler_status
from backend.i18n import init as i18n_init, set_language as i18n_set_language, get_language as i18n_get_language

# ── Import routers ────────────────────────────────
from backend.router_chat import router as chat_router, ChatRequest
from backend.router_memory import router as memory_router
from backend.router_backup import router as backup_router
from backend.router_search import router as search_router
from backend.router_conversations import router as conversations_router
from backend.router_companion import router as companion_router
from backend.router_voice import router as voice_router
from backend.router_productivity import router as productivity_router
from backend.router_stripe import router as stripe_router
from backend.router_agent import router as agent_router
from backend.router_hermes import router as hermes_router
from backend.router_os_agents import router as os_agents_router
from backend.router_embeddings import router as embeddings_router
from backend.router_calendar import router as calendar_router
from backend.router_health import router as health_router

# ── Phase 39+ Feature Routers ──
try:
    from backend.router_vision import router as vision_router
except ImportError:
    vision_router = None
try:
    from backend.router_plugins import router as plugins_router
except ImportError:
    plugins_router = None
try:
    from backend.router_workflows import router as workflows_router
except ImportError:
    workflows_router = None
try:
    from backend.router_smart import router as smart_router
except ImportError:
    smart_router = None
try:
    from backend.router_context import router as context_router
except ImportError:
    context_router = None
try:
    from backend.router_mcp import router as mcp_router
except ImportError:
    mcp_router = None
try:
    from backend.router_personal_os import router as personal_os_router
except ImportError:
    personal_os_router = None
from backend.voice_ws import init_ws_loop
from backend.shared import parse_json_body

import backend.shared as _shared

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("lexa.server")


# ══════════════════════════════════════════════════
#  APP SETUP
# ══════════════════════════════════════════════════

app = FastAPI(
    title="Lexa AI",
    description="Lokaler KI-Assistent — nur localhost",
    version=VERSION,
)

# GZip compression for faster API responses (min 500 bytes)
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS: Nur localhost erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", LOCAL_AUTH_HEADER],
)


def _ensure_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", "")
    if not request_id:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
    return request_id


# ══════════════════════════════════════════════════
#  MIDDLEWARE
# ══════════════════════════════════════════════════

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Generate UUID per request and add to response headers as X-Request-ID."""
    request_id = _ensure_request_id(request)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def local_auth_middleware(request: Request, call_next):
    """Require the per-instance local token for non-public localhost endpoints."""
    if request.method == "OPTIONS":
        return await call_next(request)
    if not is_local_auth_required() or is_local_auth_public_path(request.url.path):
        return await call_next(request)
    if request_has_valid_local_token(request):
        return await call_next(request)

    request_id = _ensure_request_id(request)
    return JSONResponse(
        status_code=401,
        content=error_payload(
            status_code=401,
            detail="Missing or invalid local Lexa authentication token.",
            request_id=request_id,
            code="local_auth_required",
            retryable=False,
        ),
        headers={"X-Request-ID": request_id},
    )


@app.middleware("http")
async def body_size_limit_middleware(request: Request, call_next):
    """Reject non-file request bodies larger than MAX_BODY_SIZE (1MB)."""
    content_type = request.headers.get("content-type", "")
    # Skip file uploads (multipart) and GET/DELETE/OPTIONS
    if request.method in ("GET", "DELETE", "OPTIONS", "HEAD"):
        return await call_next(request)
    if "multipart/form-data" in content_type:
        return await call_next(request)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
        except (ValueError, OverflowError):
            request_id = _ensure_request_id(request)
            return JSONResponse(
                status_code=400,
                content=error_payload(
                    status_code=400,
                    detail="Invalid Content-Length header.",
                    request_id=request_id,
                    code="invalid_content_length",
                ),
                headers={"X-Request-ID": request_id},
            )
        if cl > MAX_BODY_SIZE:
            request_id = _ensure_request_id(request)
            return JSONResponse(
                status_code=413,
                content=error_payload(
                    status_code=413,
                    detail=f"Request body too large (max {MAX_BODY_SIZE // 1024}KB).",
                    request_id=request_id,
                    code="payload_too_large",
                    retryable=False,
                ),
                headers={"X-Request-ID": request_id},
            )
    return await call_next(request)


@app.middleware("http")
async def log_slow_requests(request: Request, call_next):
    """Log requests taking more than SLOW_REQUEST_THRESHOLD seconds."""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    if duration > SLOW_REQUEST_THRESHOLD:
        logger.warning(f"SLOW REQUEST: {request.method} {request.url.path} took {duration:.1f}s")
    return response


# ══════════════════════════════════════════════════
#  ROUTER INCLUDES (unversioned — backward compat)
# ══════════════════════════════════════════════════

# New split routers
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(backup_router)
app.include_router(search_router)
app.include_router(conversations_router)

# Existing routers (already prefixed)
app.include_router(companion_router)
app.include_router(voice_router)
app.include_router(productivity_router)
app.include_router(stripe_router)
app.include_router(agent_router)
app.include_router(hermes_router)
app.include_router(os_agents_router)
app.include_router(embeddings_router)
app.include_router(calendar_router)
app.include_router(health_router)

# Phase 39+ Feature Routers (graceful — nur wenn verfügbar)
for _r in (vision_router, plugins_router, workflows_router, smart_router, context_router, mcp_router, personal_os_router):
    if _r is not None:
        app.include_router(_r)


# ══════════════════════════════════════════════════
#  API VERSIONING — /v1/ prefix (Task 4)
#  Both /chat and /v1/chat work. Frontend can migrate later.
# ══════════════════════════════════════════════════

from fastapi import APIRouter as _APIRouter

_v1_router = _APIRouter(prefix="/v1")

# Include all sub-routers into v1
_v1_router.include_router(chat_router)
_v1_router.include_router(memory_router)
_v1_router.include_router(backup_router)
_v1_router.include_router(search_router)
_v1_router.include_router(conversations_router)
_v1_router.include_router(companion_router)
_v1_router.include_router(voice_router)
_v1_router.include_router(productivity_router)
_v1_router.include_router(stripe_router)
_v1_router.include_router(agent_router)
_v1_router.include_router(hermes_router)
_v1_router.include_router(os_agents_router)
_v1_router.include_router(health_router)
if personal_os_router is not None:
    _v1_router.include_router(personal_os_router)

# Mount v1 on main app
app.include_router(_v1_router)


# ══════════════════════════════════════════════════
#  LIFECYCLE
# ══════════════════════════════════════════════════

async def startup_event():
    """Start background services and restore session state."""
    _shared.startup_time = time.time()

    # Initialize i18n
    i18n_init("de")

    # Initialize WebSocket voice event loop reference
    init_ws_loop(asyncio.get_running_loop())

    # Sentry status
    if _sentry_dsn:
        logger.info("Sentry error tracking enabled")
    else:
        logger.info("Sentry not configured (set SENTRY_DSN env var or keyring)")

    # Security: Warn if API keys are set via environment variables (could leak via .env files)
    _env_key_names = {
        "GROQ_API_KEY": "Groq",
        "OPENAI_API_KEY": "OpenAI",
        "GEMINI_API_KEY": "Gemini",
        "ANTHROPIC_API_KEY": "Anthropic",
    }
    for env_var, provider in _env_key_names.items():
        if os.environ.get(env_var):
            logger.warning(
                f"SECURITY: {provider} API key detected in environment variable '{env_var}'. "
                f"Environment variables can leak via .env files or process listings. "
                f"Use python-keyring instead: "
                f"python -c \"import keyring; keyring.set_password('lexa-ai', '{env_var.lower()}', 'YOUR_KEY')\""
            )

    # Startup: Verify DB is writable and accessible
    try:
        test_stats = memory.get_memory_stats()
        logger.info(f"DB OK - {test_stats.get('conversations', 0)} Conversations, {test_stats.get('memories', 0)} Memories")
    except Exception as e:
        logger.error(f"KRITISCH: DB nicht erreichbar beim Start: {e}")

    # Parallelisiert: Session-Restore + Timer-Queries gleichzeitig
    session_task = asyncio.create_task(_restore_session())
    timer_task = asyncio.create_task(_recover_timers())
    await asyncio.gather(session_task, timer_task, return_exceptions=True)

    # Start scheduler
    try:
        from companion.engine import companion
        start_scheduler(companion.execute if hasattr(companion, "execute") else None)
        logger.info("Routine-Scheduler gestartet")
    except Exception as e:
        logger.warning(f"Scheduler-Start fehlgeschlagen: {e}")

    # Pre-warm STT model in background thread (so first voice command is fast)
    def _prewarm_stt():
        try:
            from voice.stt import get_model
            get_model()
            logger.info("STT model pre-warmed successfully")
        except Exception as e:
            logger.debug(f"STT pre-warm skipped: {e}")

    import threading
    threading.Thread(target=_prewarm_stt, daemon=True, name="stt-prewarm").start()

    # ── Phase 39+ Feature Startup ──
    # Plugin Discovery
    try:
        from backend.plugin_manager import plugin_manager
        loaded = await asyncio.to_thread(plugin_manager.discover_plugins)
        logger.info(f"Plugin-System: {len(loaded)} Plugins geladen")
    except Exception as e:
        logger.warning(f"Plugin-Discovery fehlgeschlagen: {e}")

    # Workflow Scheduler
    try:
        from backend.workflows import get_workflow_engine
        wf_engine = get_workflow_engine()
        await wf_engine.start_scheduler()
        logger.info("Workflow-Scheduler gestartet")
    except Exception as e:
        logger.warning(f"Workflow-Scheduler-Start fehlgeschlagen: {e}")

    # Context Monitor
    try:
        from backend.context_monitor import context_monitor
        context_monitor.start()
        logger.info("Context-Monitor gestartet")
    except Exception as e:
        logger.warning(f"Context-Monitor-Start fehlgeschlagen: {e}")

    # Proactive Engine
    try:
        from backend.proactive import start_background as start_proactive
        await asyncio.to_thread(start_proactive)
        logger.info("Proactive-Engine gestartet")
    except Exception as e:
        logger.warning(f"Proactive-Engine-Start fehlgeschlagen: {e}")

    # MCP Registry — load config (Phase 47)
    try:
        from backend.mcp_registry import mcp_registry
        await asyncio.to_thread(mcp_registry.load_config)
        configs = mcp_registry.get_server_configs()
        logger.info(f"MCP Registry: {len(configs)} Server konfiguriert")
    except Exception as e:
        logger.warning(f"MCP Registry-Start fehlgeschlagen: {e}")


async def _restore_session():
    """Restore conversation history from last session.

    Two-tier fallback:
    1. Try session_state table (written on clean shutdown).
    2. If empty (crash / first start), load the most recent conversation
       from the conversations table so the user sees their last chat.
    """
    try:
        saved = await asyncio.to_thread(memory.session_load, "conversation_history", [])
        if saved:
            async with _history_lock:
                conversation_history.extend(saved[-MAX_HISTORY:])
            logger.info(f"Session restored: {len(conversation_history)} messages from session_state")
            return

        # Fallback: load the most recent conversation from SQLite
        messages = await asyncio.to_thread(_load_latest_conversation_messages)
        if messages:
            async with _history_lock:
                conversation_history.extend(messages[-MAX_HISTORY:])
            logger.info(f"Session restored: {len(conversation_history)} messages from latest conversation (fallback)")
    except Exception as e:
        logger.debug(f"Session restore skipped: {e}")


def _load_latest_conversation_messages() -> list[dict]:
    """Load messages from the most recent conversation in the DB.

    Returns an empty list if no conversation exists or on error.
    This runs in a worker thread (called via asyncio.to_thread).
    """
    import json as _json
    try:
        from backend.memory import _get_db
        db = _get_db()
        row = db.execute(
            "SELECT messages FROM conversations ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row and row["messages"]:
            msgs = _json.loads(row["messages"])
            if isinstance(msgs, list) and len(msgs) > 0:
                return msgs
    except Exception as e:
        logger.warning(f"[Startup] Could not load latest conversation: {e}")
    return []


async def _recover_timers():
    """Recover pending timers that fired while backend was offline."""
    try:
        from companion.engine import companion, _timer_results
        now = time.time()
        pending_timers, future_timers = await asyncio.gather(
            asyncio.to_thread(memory.timer_list_pending, now),
            asyncio.to_thread(memory.timer_list_future, now),
        )
        if pending_timers:
            logger.info(f"Timer-Recovery: {len(pending_timers)} abgelaufene Timer gefunden")
            for t in pending_timers:
                _timer_results.append({
                    "message": t["message"],
                    "fired_at": t["fire_at"],
                    "acknowledged": False,
                })
        for ft in future_timers:
            remaining = ft["fire_at"] - now
            if remaining > 0:
                companion.set_timer(int(remaining), ft["message"])
                logger.info(f"Timer neu geplant: '{ft['message']}' in {int(remaining)}s")
    except Exception as e:
        logger.debug(f"Timer-Recovery skipped: {e}")


async def shutdown_event():
    """Persist session state before shutdown."""
    try:
        async with _history_lock:
            snapshot = list(conversation_history[-MAX_HISTORY:])
        memory.session_save("conversation_history", snapshot)
        logger.info("Session state gespeichert")
    except Exception as e:
        logger.debug(f"Session save failed: {e}")

    # Disconnect all MCP servers (Phase 47)
    try:
        from backend.mcp_registry import mcp_registry
        await mcp_registry.disconnect_all()
        logger.info("MCP Server getrennt")
    except Exception as e:
        logger.debug(f"MCP shutdown: {e}")


@asynccontextmanager
async def _lifespan(app_: FastAPI):
    await startup_event()
    try:
        yield
    finally:
        await shutdown_event()


app.router.lifespan_context = _lifespan


# ══════════════════════════════════════════════════
#  HEALTH & STATUS (cached for fast polling)
# ══════════════════════════════════════════════════

@app.get("/health")
async def health(request: Request):
    cached = cache_get("health", ttl=CACHE_HEALTH_TTL)
    if cached:
        result = dict(cached)
        result.update(health_auth_fields(request))
        return result
    uptime_seconds = int(time.time() - _shared.startup_time) if _shared.startup_time else 0
    uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s"
    try:
        hermes_status = await asyncio.to_thread(get_hermes_status)
        hermes_health = {
            "state": hermes_status.get("health_state", "unknown"),
            "available": bool(hermes_status.get("available")),
            "can_run_tasks": bool(hermes_status.get("can_run_tasks")),
            "telegram_configured": bool((hermes_status.get("gateway") or {}).get("configured")),
            "summary": hermes_status.get("summary", ""),
        }
    except Exception as exc:
        logger.warning(f"Hermes health check failed: {exc}")
        hermes_health = {
            "state": "unknown",
            "available": False,
            "can_run_tasks": False,
            "telegram_configured": False,
            "summary": "Hermes health check failed.",
        }
    result = {
        "status": "ok",
        "service": "lexa-ai",
        "version": VERSION,
        "uptime": uptime_str,
        "uptime_seconds": uptime_seconds,
        "sentry": bool(_sentry_dsn),
        "hermes": hermes_health,
    }
    cache_set("health", result)
    result = dict(result)
    result.update(health_auth_fields(request))
    return result


@app.get("/health/tools")
async def tool_health():
    """External tool availability check (Git, Docker, ffmpeg, etc.)."""
    from companion.tool_health import get_health_summary
    return await asyncio.to_thread(get_health_summary)


@app.get("/i18n/language")
async def get_language():
    """Get the current backend language."""
    return {"language": i18n_get_language()}


@app.post("/i18n/language")
async def set_language(request: Request):
    """Set the backend language (de/en)."""
    body = await parse_json_body(request)
    lang = body.get("language", "").strip().lower()
    if not lang or lang not in ("de", "en"):
        request_id = _ensure_request_id(request)
        return JSONResponse(
            status_code=400,
            content=error_payload(
                status_code=400,
                detail="Invalid language. Allowed: de, en",
                request_id=request_id,
                code="invalid_language",
            ),
            headers={"X-Request-ID": request_id},
        )
    ok = i18n_set_language(lang)
    return {"success": ok, "language": i18n_get_language()}


@app.get("/diagnostics")
async def diagnostics():
    """Umfassender System-Status für Debugging."""
    import sys
    import platform

    # Memory DB info
    try:
        mem_stats = await asyncio.to_thread(memory.get_memory_stats)
    except Exception:
        mem_stats = {}

    # AI status
    try:
        ai_info = await asyncio.to_thread(get_ai_status)
    except Exception:
        ai_info = {}

    # Scheduler status
    try:
        sched = get_scheduler_status()
    except Exception:
        sched = {}

    try:
        hermes_info = await asyncio.to_thread(get_hermes_status)
    except Exception as exc:
        hermes_info = {"status": "error", "health_state": "unknown", "summary": str(exc)}

    # DB file size — use LEXA_DATA_DIR for packaged builds
    _diag_data_dir = Path(os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent)))
    db_size_kb = 0
    try:
        db_path = _diag_data_dir / "lexa_memory.db"
        if db_path.exists():
            db_size_kb = round(db_path.stat().st_size / 1024, 1)
    except Exception:
        pass

    # Audit log size
    audit_size_kb = 0
    try:
        audit_path = _diag_data_dir / "audit.log"
        if audit_path.exists():
            audit_size_kb = round(audit_path.stat().st_size / 1024, 1)
    except Exception:
        pass

    return {
        "status": "ok",
        "version": VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "memory": mem_stats,
        "ai": ai_info,
        "hermes": hermes_info,
        "scheduler": sched,
        "db_size_kb": db_size_kb,
        "audit_log_size_kb": audit_size_kb,
        "conversation_history_len": len(conversation_history),
    }


@app.get("/ai/status")
async def ai_status():
    """Get AI provider status."""
    result = await asyncio.to_thread(get_ai_status)
    if isinstance(result, dict):
        result["status"] = "ok"
    return result


@app.get("/scheduler/status")
async def scheduler_status():
    """Get routine scheduler status."""
    result = get_scheduler_status()
    if isinstance(result, dict):
        result["status"] = "ok"
    return result


# ══════════════════════════════════════════════════
#  AI TITLE & MODEL SELECTION
# ══════════════════════════════════════════════════

@app.post("/ai/title")
async def ai_generate_title(req: ChatRequest):
    """Generate an AI-powered conversation title."""
    try:
        title = await asyncio.to_thread(generate_title, req.message)
        return {"status": "ok", "title": title}
    except Exception as e:
        logger.warning(f"AI title generation failed: {e}")
        raise HTTPException(status_code=502, detail="AI title generation failed")


@app.get("/ai/models")
async def ai_models():
    """Get available AI models and current selection."""
    result = get_ai_models()
    if isinstance(result, dict):
        result["status"] = "ok"
    return result


@app.post("/ai/models")
async def set_ai_model_endpoint(req: Request):
    """Set the active AI model."""
    data = await parse_json_body(req)
    model_id = data.get("model", "")
    result = set_active_ai_model(model_id)
    return {"status": result, "current": get_ai_models()}


# ══════════════════════════════════════════════════
#  EXCEPTION HANDLERS
# ══════════════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return the canonical Lexa error envelope for HTTP errors."""
    headers = dict(getattr(exc, "headers", None) or {})
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            status_code=exc.status_code,
            detail=exc.detail,
            request_id=request_id or "",
            retryable=exc.status_code in (408, 429, 502, 503, 504),
        ),
        headers=headers if headers else None,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return validation errors in the same envelope while keeping detail."""
    request_id = getattr(request.state, "request_id", "")
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=422,
        content=error_payload(
            status_code=422,
            detail=jsonable_encoder(exc.errors()),
            request_id=request_id,
            code="validation_error",
            retryable=False,
        ),
        headers=headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — return 500 with consistent format."""
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content=error_payload(
            status_code=500,
            detail="Internal server error",
            request_id=getattr(request.state, "request_id", ""),
            code="internal_error",
            retryable=True,
        ),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
