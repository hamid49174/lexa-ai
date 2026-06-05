"""Hermes Agent API router."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.agent_protocol import redacted_summary
from backend.obsidian_context import build_obsidian_context_payload, format_obsidian_context_for_prompt
from backend.hermes_adapter import (
    configure_hermes_telegram,
    get_hermes_gateway_log_summary,
    get_hermes_gateway_autostart_status,
    get_hermes_status,
    get_hermes_telegram_command_selftest,
    get_hermes_telegram_status,
    improve_lexa_with_hermes,
    run_hermes_task,
    set_hermes_gateway_autostart,
)
from backend.security import audit_log, check_rate_limit, sanitize_input

logger = logging.getLogger("lexa.hermes_router")

router = APIRouter(prefix="/hermes", tags=["hermes"])

_DRAFT_APPROVALS = {"pending", "approved", "rejected", "conflict", "missing"}
_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc)/[^\s\"'<>|]+)"
)
_TELEGRAM_TOKEN_RE = re.compile(r"\b\d{5,20}:[A-Za-z0-9_-]{20,120}\b")
_LEXA_LICENSE_RE = re.compile(r"\bLEXA-[A-Z0-9]{5}(?:-[A-Z0-9]{5}){3}\b", re.IGNORECASE)


class HermesTaskRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    mode: Literal["general", "lexa_improve", "os_context"] = "general"
    timeoutSeconds: int = Field(120, ge=10, le=600)


class HermesImproveRequest(BaseModel):
    focus: str = Field("", max_length=1000)
    timeoutSeconds: int = Field(180, ge=10, le=600)


class HermesTelegramConfigureRequest(BaseModel):
    botToken: str = Field(..., min_length=20, max_length=200)
    homeChannel: str = Field("", max_length=128)
    homeChannelName: str = Field("Lexa", max_length=80)


class HermesGatewayAutostartRequest(BaseModel):
    enabled: bool = True


class HermesContextRequest(BaseModel):
    topic: str = Field("", max_length=240)
    maxFiles: int = Field(7, ge=1, le=14)
    bodyChars: int = Field(700, ge=160, le=1800)
    includePreviews: bool = True


class HermesDraftRequest(BaseModel):
    body: str = Field(..., min_length=3, max_length=4000)
    title: str = Field("", max_length=120)
    targetPath: str = Field("", max_length=240)
    tags: list[str] = Field(default_factory=list, max_length=8)


def _slug(value: str, fallback: str = "telegram-draft") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:80]
    return slug or fallback


def _client_safe_error(exc: Exception, *, max_chars: int = 220) -> str:
    """Return a compact client-facing error without local paths or secrets."""
    text = redacted_summary(str(exc), max_chars=max_chars)
    text = _TELEGRAM_TOKEN_RE.sub("[telegram-token-redacted]", text)
    text = _LEXA_LICENSE_RE.sub("[license-redacted]", text)
    text = _LOCAL_PATH_RE.sub("[local-path-redacted]", text)
    return text or "Details wurden lokal protokolliert."


def _hermes_error_detail(prefix: str, exc: Exception) -> str:
    return f"{prefix}: {_client_safe_error(exc)}"


def _draft_title(body: str, explicit: str = "") -> str:
    title = (explicit or "").strip()
    if title:
        return title[:120]
    first_line = next((line.strip().lstrip("#").strip() for line in body.splitlines() if line.strip()), "")
    return (first_line or "Hermes Telegram Draft")[:120]


def _safe_tags(values: list[str]) -> list[str]:
    tags: set[str] = {"telegram", "hermes", "lexa", "draft"}
    for value in values:
        tag = re.sub(r"[^a-z0-9_-]+", "-", str(value).strip().lower()).strip("-")[:40]
        if tag:
            tags.add(tag)
    return sorted(tags)[:8]


def _safe_target_path(raw: str, title: str) -> str:
    value = (raw or "").strip().replace("\\", "/")
    if not value:
        day = datetime.now(timezone.utc).date().isoformat()
        return f"05_Memory/Session/{day}_telegram_hermes_{_slug(title)}.md"
    if Path(value).is_absolute() or value.startswith("/") or ".." in value.split("/"):
        raise HTTPException(status_code=400, detail="targetPath must be an OS-relative Markdown path")
    if Path(value).suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="targetPath must point to a Markdown file")
    if value.startswith("06_Inbox/Drafts/"):
        raise HTTPException(status_code=400, detail="targetPath should be the proposed destination, not the draft file")
    return value


def _draft_markdown_body(title: str, body: str, target_path: str) -> str:
    clean_body = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    return "\n".join([
        f"# {title}",
        "",
        "## Source",
        "",
        "- Telegram via Hermes `/lexa_draft`.",
        "",
        "## Candidate Destination",
        "",
        f"- `{target_path}`",
        "",
        "## User Request",
        "",
        clean_body,
        "",
        "## Proposed Update",
        "",
        "Review this request and decide which stable OS context, if any, should be updated.",
        "",
        "## Safety Boundary",
        "",
        "- This draft was created from Telegram and did not modify stable OS files.",
        "- Stable OS files remain Draft/Approval protected.",
        "",
        "## Approval",
        "",
        "- [ ] Approved",
        "- [ ] Rejected",
        "",
    ])


def _compact_draft(draft: dict) -> dict:
    tags = draft.get("tags") if isinstance(draft.get("tags"), list) else []
    return {
        "title": draft.get("title") or "Untitled",
        "path": draft.get("path"),
        "approval": draft.get("approval") or "unknown",
        "memoryLevel": draft.get("memory_level"),
        "source": draft.get("source"),
        "created": draft.get("created"),
        "updated": draft.get("updated"),
        "tags": [str(tag) for tag in tags[:6] if tag],
    }


def _compact_context_file(file_info: dict) -> dict:
    tags = file_info.get("tags") if isinstance(file_info.get("tags"), list) else []
    return {
        "title": file_info.get("title") or file_info.get("path") or "OS file",
        "path": file_info.get("path"),
        "memoryLevel": file_info.get("memory_level"),
        "tags": [str(tag) for tag in tags[:6] if tag],
        "score": file_info.get("score"),
    }


def _state(ok: bool) -> str:
    return "ok" if ok else "attention"


def _draft_count_line(counts: dict) -> str:
    return (
        f"{counts.get('pending', 0)} pending, "
        f"{counts.get('approved', 0)} approved, "
        f"{counts.get('rejected', 0)} rejected"
    )


def _open_tasks_from_text(text: str, limit: int = 8) -> list[str]:
    tasks: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- [ ] "):
            continue
        task = line[6:].strip().rstrip(".")
        if not task or task.lower().startswith("later:"):
            continue
        tasks.append(task)
        if len(tasks) >= limit:
            break
    return tasks


def _read_next_work_tasks(hermes: dict, limit: int = 6) -> list[str]:
    raw_root = str(hermes.get("personal_os_root") or "").strip()
    if not raw_root:
        return []
    root = Path(raw_root)
    path = root / "08_Lexa" / "Tasks" / "Lexa_Next_Work.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:80_000]
    except OSError:
        return []
    tasks = _open_tasks_from_text(text, limit=80)
    preferred = [
        task for task in tasks
        if any(term in task.lower() for term in ("hermes", "telegram", "obsidian", "os", "backend", "context", "cockpit"))
    ]
    return (preferred or tasks)[:limit]


async def _safe_to_thread(fn, *args) -> dict:
    try:
        result = await asyncio.to_thread(fn, *args)
        return result if isinstance(result, dict) else {}
    except Exception as exc:
        logger.warning("Hermes overview read failed for %s: %s", getattr(fn, "__name__", fn), exc)
        return {"status": "error", "error": _client_safe_error(exc)}


async def _safe_draft_queue() -> dict:
    try:
        return await list_hermes_os_drafts("all", 50, True)
    except Exception as exc:
        logger.warning("Hermes overview draft read failed: %s", exc)
        return {"ok": False, "counts": {}, "drafts": [], "errors": [{"error": _client_safe_error(exc)}]}


async def build_hermes_overview(include_context: bool = True) -> dict:
    """Build one compact Lexa/Hermes/Personal OS overview for app and Telegram."""
    hermes_task = _safe_to_thread(get_hermes_status)
    telegram_task = _safe_to_thread(get_hermes_telegram_status)
    autostart_task = _safe_to_thread(get_hermes_gateway_autostart_status)
    logs_task = _safe_to_thread(get_hermes_gateway_log_summary, 120)
    drafts_task = _safe_draft_queue()
    context_task = asyncio.to_thread(
        build_obsidian_context_payload,
        topic="Lexa Hermes Personal OS status overview",
        max_files=5,
        body_chars=300,
        include_previews=False,
    ) if include_context else None

    hermes, telegram, autostart, logs, drafts = await asyncio.gather(
        hermes_task,
        telegram_task,
        autostart_task,
        logs_task,
        drafts_task,
    )
    if not isinstance(drafts, dict):
        drafts = {}
    context = {}
    if context_task is not None:
        try:
            context_result = await context_task
            context = context_result if isinstance(context_result, dict) else {}
        except Exception as exc:
            logger.warning("Hermes overview context read failed: %s", exc)
            context = {"ok": False, "error": _client_safe_error(exc)}

    obsidian = hermes.get("obsidian_context") if isinstance(hermes.get("obsidian_context"), dict) else {}
    context_files = context.get("files") if isinstance(context.get("files"), list) else []
    draft_counts = drafts.get("counts") if isinstance(drafts.get("counts"), dict) else {}
    log_counts = logs.get("counts") if isinstance(logs.get("counts"), dict) else {}
    next_tasks = _read_next_work_tasks(hermes)

    backend_ok = True
    hermes_ok = hermes.get("health_state") == "ready"
    telegram_ok = bool(telegram.get("configured"))
    autostart_ok = bool(autostart.get("enabled"))
    obsidian_ok = bool(obsidian.get("ok")) or bool(context.get("ok"))
    logs_ok = logs.get("status") == "ok" and logs.get("health_state") == "ok"
    drafts_ok = not draft_counts.get("invalid") and not draft_counts.get("missing")

    checks = [
        {"id": "backend", "label": "Lexa backend", "state": _state(backend_ok), "detail": "Backend route is live."},
        {"id": "hermes", "label": "Hermes", "state": _state(hermes_ok), "detail": hermes.get("summary") or hermes.get("health_state") or "unknown"},
        {"id": "telegram", "label": "Telegram", "state": _state(telegram_ok), "detail": "configured" if telegram_ok else "not configured"},
        {"id": "autostart", "label": "Gateway autostart", "state": _state(autostart_ok), "detail": "enabled" if autostart_ok else "disabled"},
        {"id": "obsidian", "label": "Obsidian/Personal OS", "state": _state(obsidian_ok), "detail": obsidian.get("summary") or "bounded context"},
        {"id": "logs", "label": "Gateway logs", "state": _state(logs_ok), "detail": logs.get("summary") or "no summary"},
        {"id": "drafts", "label": "Review drafts", "state": _state(drafts_ok), "detail": _draft_count_line(draft_counts)},
    ]
    health_state = "ready" if all(check["state"] == "ok" for check in checks[:6]) and drafts_ok else "attention"
    next_action = next_tasks[0] if next_tasks else "Build the visible OS/Hermes cockpit in Lexa."
    summary = (
        "Lexa/Hermes/OS ist arbeitsfaehig: "
        f"Hermes {hermes.get('health_state', 'unknown')}, "
        f"Telegram {'bereit' if telegram_ok else 'nicht bereit'}, "
        f"Autostart {'an' if autostart_ok else 'aus'}, "
        f"Drafts {_draft_count_line(draft_counts)}, "
        f"Logs {'ok' if logs_ok else 'Achtung'}."
    )

    return {
        "ok": health_state == "ready",
        "healthState": health_state,
        "summary": summary,
        "nextAction": next_action,
        "checks": checks,
        "counts": {
            "drafts": draft_counts,
            "logs": log_counts,
            "contextFiles": len(context_files),
        },
        "capabilities": {
            "backendEndpoints": [
                "/hermes/status",
                "/hermes/overview",
                "/hermes/context",
                "/hermes/draft",
                "/hermes/drafts",
                "/hermes/gateway/logs",
                "/hermes/gateway/autostart",
                "/hermes/telegram/status",
                "/hermes/telegram/commands/selftest",
                "/health/startup",
            ],
            "telegramCommands": [
                "/lexa_status",
                "/lexa_overview",
                "/lexa_logs",
                "/lexa_tasks",
                "/lexa_context",
                "/lexa_draft",
                "/lexa_drafts",
            ],
            "stableWrites": "draft-approval-only",
        },
        "contextFiles": [_compact_context_file(file_info) for file_info in context_files[:5] if isinstance(file_info, dict)],
        "nextTasks": next_tasks,
        "safeMode": True,
        "telegramText": "\n".join([
            "Lexa/Hermes Overview:",
            f"- Stand: {summary}",
            f"- Obsidian/OS: {'ok' if obsidian_ok else 'Achtung'}; {len(context_files)} Kontextdateien im Overview.",
            f"- Naechste Aktion: {next_action}",
            "- Grenze: stabile OS-Dateien bleiben Draft/Approval-geschuetzt.",
        ]),
    }


async def create_hermes_os_draft(req: HermesDraftRequest) -> dict:
    """Create a Personal OS review draft through the MCP write boundary."""
    from backend.router_personal_os import _call_personal_os_tool

    body = sanitize_input(req.body)
    title = _draft_title(body, sanitize_input(req.title))
    target_path = _safe_target_path(req.targetPath, title)
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    day = now[:10]
    frontmatter = {
        "id": f"pos-{day.replace('-', '')}-hermes-telegram-{_slug(title)}",
        "type": "draft",
        "title": title,
        "status": "draft",
        "memory_level": "session",
        "created": now,
        "updated": now,
        "owner": "agent",
        "confidence": "medium",
        "source": "user",
        "tags": _safe_tags(req.tags),
        "related": ["08_Lexa/Tasks/Lexa_OS_Live_Status.md", "08_Lexa/Architecture/Hermes_Capabilities.md"],
    }
    result = await _call_personal_os_tool("os_write_draft", {
        "filepath": target_path,
        "frontmatter": frontmatter,
        "markdownBody": _draft_markdown_body(title, body, target_path),
        "agentName": "HermesTelegramDraft",
        "reason": "Hermes Telegram /lexa_draft review proposal",
    })
    return {
        "success": result.get("status") == "draft",
        "status": result.get("status"),
        "title": title,
        "targetPath": target_path,
        "draftPath": result.get("draft"),
        "file": result.get("file"),
        "safeMode": True,
        "note": "Stable OS files were not modified; review the draft before applying anything durable.",
    }


async def list_hermes_os_drafts(approval: str, max_drafts: int, hide_smoke: bool) -> dict:
    """Return a compact Personal OS draft queue for Hermes/Telegram."""
    from backend.router_personal_os import _call_personal_os_tool

    approval = (approval or "pending").strip().lower()
    if approval != "all" and approval not in _DRAFT_APPROVALS:
        raise HTTPException(status_code=400, detail="Invalid draft approval filter")

    arguments: dict[str, object] = {
        "hideSmoke": hide_smoke,
        "maxDrafts": max_drafts,
        "agentName": "HermesTelegramDrafts",
        "reason": "Hermes Telegram /lexa_drafts review queue read",
    }
    if approval != "all":
        arguments["approvals"] = [approval]

    queue = await _call_personal_os_tool("os_list_drafts", arguments)
    drafts = queue.get("drafts") if isinstance(queue.get("drafts"), list) else []
    return {
        "ok": bool(queue.get("ok", True)),
        "approval": approval,
        "counts": queue.get("counts") if isinstance(queue.get("counts"), dict) else {},
        "drafts": [_compact_draft(draft) for draft in drafts[:max_drafts] if isinstance(draft, dict)],
        "errors": queue.get("errors") if isinstance(queue.get("errors"), list) else [],
        "truncated": bool(queue.get("truncated")),
        "safeMode": True,
        "note": "Read-only draft queue view; stable OS files were not modified.",
    }


@router.get("/status")
async def hermes_status():
    """Return Hermes integration readiness."""
    return await asyncio.to_thread(get_hermes_status)


@router.get("/overview")
async def hermes_overview(includeContext: bool = Query(default=True)):
    """Return one compact Lexa/Hermes/Personal OS overview for app and Telegram."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Overview-Anfragen.")

    audit_log("hermes", "overview", f"includeContext={includeContext}")
    try:
        return await build_hermes_overview(includeContext)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Hermes overview failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes-Overview konnte nicht gebaut werden", exc)) from exc


@router.post("/context")
async def hermes_context(req: HermesContextRequest):
    """Return a Hermes-ready Obsidian/Personal OS context bootstrap."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Kontext-Anfragen.")

    topic = sanitize_input(req.topic)
    audit_log("hermes", "context", f"topicChars={len(topic)} includePreviews={req.includePreviews}")
    try:
        payload = await asyncio.to_thread(
            build_obsidian_context_payload,
            topic=topic,
            max_files=req.maxFiles,
            body_chars=req.bodyChars,
            include_previews=req.includePreviews,
        )
        prompt = await asyncio.to_thread(format_obsidian_context_for_prompt, payload)
    except Exception as exc:
        logger.exception("Hermes context failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes-Kontext konnte nicht gebaut werden", exc)) from exc
    return {
        "ok": True,
        "context": payload,
        "prompt": prompt,
    }


@router.post("/draft")
async def hermes_draft(req: HermesDraftRequest):
    """Create a safe Personal OS review draft from Hermes/Telegram input."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Draft-Anfragen.")

    audit_log(
        "hermes",
        "draft_create",
        f"titleChars={len(sanitize_input(req.title))} bodyChars={len(sanitize_input(req.body))} targetSet={bool(req.targetPath.strip())}",
    )
    try:
        return await create_hermes_os_draft(req)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Hermes draft create failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes-Draft konnte nicht erstellt werden", exc)) from exc


@router.get("/drafts")
async def hermes_drafts(
    approval: str = Query(default="pending", max_length=20),
    maxDrafts: int = Query(default=20, ge=1, le=50),
    hideSmoke: bool = Query(default=True),
):
    """List a compact Personal OS review-draft queue for Hermes/Telegram."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Draft-Anfragen.")

    audit_log("hermes", "drafts_list", f"approval={approval or 'pending'} hideSmoke={hideSmoke}")
    try:
        return await list_hermes_os_drafts(approval, maxDrafts, hideSmoke)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Hermes draft list failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes-Drafts konnten nicht gelesen werden", exc)) from exc


@router.get("/telegram/status")
async def hermes_telegram_status():
    """Return Telegram readiness for the Lexa-local Hermes install."""
    return await asyncio.to_thread(get_hermes_telegram_status)


@router.get("/telegram/commands/selftest")
async def hermes_telegram_commands_selftest(includeSamples: bool = Query(default=True)):
    """Run local Lexa Telegram command checks without sending Telegram messages."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Telegram-Anfragen.")
    audit_log("hermes", "telegram_command_selftest", f"includeSamples={includeSamples}")
    return await asyncio.to_thread(get_hermes_telegram_command_selftest, includeSamples)


@router.get("/gateway/autostart")
async def hermes_gateway_autostart_status():
    """Return Windows-login autostart status for the Hermes gateway."""
    return await asyncio.to_thread(get_hermes_gateway_autostart_status)


@router.get("/gateway/logs")
async def hermes_gateway_logs(lines: int = Query(160, ge=20, le=1000)):
    """Return a bounded, redacted Hermes gateway log summary."""
    return await asyncio.to_thread(get_hermes_gateway_log_summary, lines)


@router.post("/gateway/autostart")
async def hermes_gateway_autostart_set(req: HermesGatewayAutostartRequest):
    """Enable or disable Hermes gateway startup at Windows login."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Autostart-Anfragen.")
    audit_log("hermes", "gateway_autostart", f"enabled={req.enabled}")
    try:
        return await asyncio.to_thread(set_hermes_gateway_autostart, req.enabled)
    except Exception as exc:
        logger.exception("Hermes gateway autostart update failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes-Gateway-Autostart fehlgeschlagen", exc))


@router.post("/telegram/configure")
async def hermes_telegram_configure(req: HermesTelegramConfigureRequest):
    """Save Telegram settings into Hermes' Lexa-local .env file."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Telegram-Anfragen.")

    home_channel = sanitize_input(req.homeChannel)
    home_channel_name = sanitize_input(req.homeChannelName)
    audit_log("hermes", "telegram_configure", f"homeChannelSet={bool(home_channel)}")
    try:
        return await asyncio.to_thread(
            configure_hermes_telegram,
            req.botToken,
            home_channel,
            home_channel_name,
        )
    except Exception as exc:
        logger.exception("Hermes Telegram configure failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes-Telegram-Setup fehlgeschlagen", exc))


@router.post("/run")
async def hermes_run(req: HermesTaskRequest):
    """Run a bounded Hermes task through Lexa's adapter."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Anfragen.")

    message = sanitize_input(req.message)
    audit_log("hermes", "run", f"mode={req.mode} chars={len(message)}")
    try:
        return await asyncio.to_thread(run_hermes_task, message, req.mode, req.timeoutSeconds)
    except Exception as exc:
        logger.exception("Hermes run failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes konnte nicht gestartet werden", exc))


@router.post("/improve-lexa")
async def hermes_improve_lexa(req: HermesImproveRequest):
    """Ask Hermes for a controlled Lexa improvement pass."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Hermes-Anfragen.")

    focus = sanitize_input(req.focus)
    audit_log("hermes", "improve_lexa", f"focusChars={len(focus)}")
    try:
        return await asyncio.to_thread(improve_lexa_with_hermes, focus, req.timeoutSeconds)
    except Exception as exc:
        logger.exception("Hermes improve failed")
        raise HTTPException(status_code=502, detail=_hermes_error_detail("Hermes-Verbesserung fehlgeschlagen", exc))
