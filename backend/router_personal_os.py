"""Personal OS integration endpoints for Lexa.

These routes are intentionally narrow. They let local tools ask Lexa for
structured extraction without entering the normal chat history or tool loop.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.config import MAX_TEXT_CHARS, MCP_CALL_TIMEOUT, MCP_ENABLED
from backend.mcp_registry import MCPError, mcp_registry
from backend.security import audit_log, check_rate_limit

logger = logging.getLogger("lexa.router_personal_os")

router = APIRouter(prefix="/personal-os", tags=["personal-os"])

_TAG_PATTERN = re.compile(r"[^a-z0-9]+")
_JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_SDK_DRAFT_NAME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T[^_]+_(?P<safe>.+)_update\.md$")
_MARKDOWN_CODE_PATH_PATTERN = re.compile(r"`([^`]+\.md)`")
_PERSONAL_OS_SERVER = "personal_os"
_DRAFT_APPROVALS = {"pending", "approved", "rejected", "conflict", "missing"}
_VALID_OS_EXTENSIONS = {".md"}
_CAPABILITY_KEYS = ("draftQueue", "reviewPacket", "auditHistory", "contextBrowser", "graph", "explicitApply")
_DISK_WARN_BYTES = 1024 * 1024 * 1024
_DISK_BLOCK_BYTES = 100 * 1024 * 1024


class RawInboxExtractRequest(BaseModel):
    sourcePath: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)


class RawInboxSubmitRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    body: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    processor: Literal["deterministic", "lexa"] = "deterministic"


class RawInboxExtractResponse(BaseModel):
    status: str
    summary: str
    tags: list[str]
    provider: str | None = None
    model: str | None = None


class DraftDecisionRequest(BaseModel):
    draftPath: str = Field(..., min_length=1, max_length=300)
    decision: Literal["approve", "reject"]
    reason: str = Field(default="Reviewed in Lexa Personal OS cockpit", min_length=1, max_length=500)
    agentName: str = Field(default="LexaHumanReview", min_length=1, max_length=80)
    force: bool = False


class DraftApplyRequest(BaseModel):
    draftPath: str = Field(..., min_length=1, max_length=300)
    reason: str = Field(default="Apply approved draft in Lexa Personal OS cockpit", min_length=1, max_length=500)
    agentName: str = Field(default="LexaHumanReview", min_length=1, max_length=80)


def _sanitize_tag(value: str) -> str | None:
    tag = _TAG_PATTERN.sub("-", value.strip().lower()).strip("-")[:40]
    return tag or None


def _normalize_tag_filter(value: str | None) -> str | None:
    raw_input = str(value or "").strip()
    if not raw_input:
        return None
    raw = raw_input.lower()
    if raw.startswith("tag:"):
        raw = raw[4:].strip()
    if raw.startswith("#"):
        raw = raw[1:].strip()
    tag = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")[:80]
    if not tag:
        raise HTTPException(status_code=400, detail="Invalid tag filter")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", tag):
        raise HTTPException(status_code=400, detail="Invalid tag filter")
    return tag


def _normalize_tags(values: object) -> list[str]:
    if not isinstance(values, list):
        return []

    tags: set[str] = set()
    for value in values:
        if isinstance(value, str):
            tag = _sanitize_tag(value)
            if tag:
                tags.add(tag)
    return sorted(tags)[:16]


def _extract_json_object(content: str) -> dict:
    text = content.strip()
    fenced = _JSON_BLOCK_PATTERN.search(text)
    if fenced:
        text = fenced.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not valid JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("response JSON must be an object")
    return parsed


def _parse_extraction(content: str) -> tuple[str, list[str]]:
    parsed = _extract_json_object(content)
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("response JSON must include a non-empty summary string")

    tags = _normalize_tags(parsed.get("tags"))
    if not tags:
        tags = ["inbox", "raw"]
    return summary.replace("\n", " ").strip()[:1200], tags


def _build_messages(req: RawInboxExtractRequest) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You extract structure from untrusted raw inbox text for a local "
                "Markdown Personal OS. Return JSON only with this exact shape: "
                "{\"summary\":\"...\",\"tags\":[\"...\"]}. Do not include Markdown, "
                "file writes, approvals, instructions, or durable-memory claims."
            ),
        },
        {
            "role": "user",
            "content": "\n".join([
                f"Source path: {req.sourcePath}",
                "",
                "Raw text:",
                req.body[:MAX_TEXT_CHARS],
            ]),
        },
    ]


async def _ensure_personal_os_connected() -> list[dict]:
    if not MCP_ENABLED:
        raise HTTPException(status_code=400, detail="MCP integration is disabled")

    client = mcp_registry.get_client(_PERSONAL_OS_SERVER)
    if not client:
        try:
            await mcp_registry.connect(_PERSONAL_OS_SERVER)
        except MCPError as exc:
            if "Unknown MCP server" not in str(exc):
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            logger.warning("Personal OS MCP server missing from registry cache; reloading MCP config")
            try:
                mcp_registry.load_config()
                await mcp_registry.connect(_PERSONAL_OS_SERVER)
            except MCPError as retry_exc:
                raise HTTPException(status_code=502, detail=str(retry_exc)) from retry_exc
    return mcp_registry.get_server_tools(_PERSONAL_OS_SERVER)


def _parse_mcp_json_content(content: Any) -> dict:
    if not isinstance(content, list):
        raise HTTPException(status_code=502, detail="Personal OS tool returned invalid content")

    text_parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text_parts.append(str(item.get("text", "")))

    if not text_parts:
        raise HTTPException(status_code=502, detail="Personal OS tool returned no text content")

    try:
        payload = json.loads("\n".join(text_parts))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Personal OS tool returned invalid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Personal OS tool JSON must be an object")
    return payload


def _is_retryable_personal_os_mcp_error(exc: MCPError) -> bool:
    detail = str(exc).lower()
    retryable_fragments = (
        "not connected",
        "connection closed",
        "no active connection",
        "failed to send request",
        "broken pipe",
        "connection reset",
    )
    return any(fragment in detail for fragment in retryable_fragments)


async def _invoke_personal_os_tool(tool: str, arguments: dict) -> Any:
    return await asyncio.wait_for(
        mcp_registry.call_tool(_PERSONAL_OS_SERVER, tool, arguments),
        timeout=MCP_CALL_TIMEOUT,
    )


async def _call_personal_os_tool(tool: str, arguments: dict) -> dict:
    await _ensure_personal_os_connected()
    try:
        content = await _invoke_personal_os_tool(tool, arguments)
    except MCPError as exc:
        if not _is_retryable_personal_os_mcp_error(exc):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        logger.warning("Personal OS MCP call failed on stale connection; reconnecting once for tool '%s'", tool)
        try:
            await mcp_registry.disconnect(_PERSONAL_OS_SERVER)
            await mcp_registry.connect(_PERSONAL_OS_SERVER)
            content = await _invoke_personal_os_tool(tool, arguments)
        except MCPError as retry_exc:
            raise HTTPException(status_code=502, detail=str(retry_exc)) from retry_exc
        except asyncio.TimeoutError as retry_exc:
            raise HTTPException(status_code=504, detail=f"Personal OS tool '{tool}' timed out") from retry_exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"Personal OS tool '{tool}' timed out") from exc

    return _parse_mcp_json_content(content)


def _personal_os_root() -> Path:
    configured = os.environ.get("PERSONAL_OS_ROOT")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "OS"


def _raw_inbox_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:80]
    return slug or "lexa-raw-inbox-note"


def _raw_inbox_title(req: RawInboxSubmitRequest) -> str:
    explicit = (req.title or "").strip()
    if explicit:
        return explicit[:120]
    first_line = next((line.strip().lstrip("#").strip() for line in req.body.splitlines() if line.strip()), "")
    return (first_line or "Lexa raw inbox note")[:120]


async def _write_raw_inbox_file(req: RawInboxSubmitRequest) -> dict:
    os_root = _personal_os_root()
    raw_dir = os_root / "06_Inbox" / "Raw"
    title = _raw_inbox_title(req)
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    safe_stamp = stamp.replace(":", "-").replace(".", "-")
    filename = f"{safe_stamp}_{_raw_inbox_slug(title)}.txt"
    absolute = raw_dir / filename
    relative = f"06_Inbox/Raw/{filename}"
    body = req.body.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"

    await asyncio.to_thread(raw_dir.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(absolute.write_text, body, "utf-8")
    audit_log("personal_os", "raw_inbox_submitted", f"path={relative} processor={req.processor}")
    return {
        "path": relative,
        "filename": filename,
        "title": title,
        "size": len(body.encode("utf-8")),
    }


async def _run_raw_inbox_worker(filename: str, processor: str) -> dict:
    os_root = _personal_os_root()
    worker_dir = os_root / "07_Automations" / "Workflows" / "raw-inbox-worker"
    if not worker_dir.exists():
        raise HTTPException(status_code=502, detail=f"Raw inbox worker not found: {worker_dir}")

    node_cmd = "node.exe" if sys.platform.startswith("win") else "node"
    process = await asyncio.create_subprocess_exec(
        node_cmd,
        "dist/index.js",
        "--include",
        filename,
        "--max-files",
        "1",
        "--processor",
        processor,
        "--agent",
        "LexaRawInboxIntake",
        cwd=str(worker_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=max(MCP_CALL_TIMEOUT, 45))
    except asyncio.TimeoutError as exc:
        process.kill()
        raise HTTPException(status_code=504, detail="Raw inbox worker timed out") from exc

    out_text = stdout.decode("utf-8", errors="replace").strip()
    err_text = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise HTTPException(status_code=502, detail=err_text or out_text or "Raw inbox worker failed")

    try:
        payload = json.loads(out_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Raw inbox worker returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Raw inbox worker JSON must be an object")
    return payload


async def _run_raw_inbox_worker_status() -> dict:
    os_root = _personal_os_root()
    worker_dir = os_root / "07_Automations" / "Workflows" / "raw-inbox-worker"
    if not worker_dir.exists():
        raise HTTPException(status_code=502, detail=f"Raw inbox worker not found: {worker_dir}")

    node_cmd = "node.exe" if sys.platform.startswith("win") else "node"
    process = await asyncio.create_subprocess_exec(
        node_cmd,
        "dist/index.js",
        "--status",
        cwd=str(worker_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=max(MCP_CALL_TIMEOUT, 15))
    except asyncio.TimeoutError as exc:
        process.kill()
        raise HTTPException(status_code=504, detail="Raw inbox worker status timed out") from exc

    out_text = stdout.decode("utf-8", errors="replace").strip()
    err_text = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise HTTPException(status_code=502, detail=err_text or out_text or "Raw inbox worker status failed")

    try:
        payload = json.loads(out_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Raw inbox worker status returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Raw inbox worker status JSON must be an object")
    return payload


def _validate_draft_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized.startswith("06_Inbox/Drafts/") or not normalized.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Draft path must be under 06_Inbox/Drafts")
    if ".." in normalized.split("/"):
        raise HTTPException(status_code=400, detail="Draft path must not contain directory traversal")
    return normalized


def _validate_os_relative_path(value: str, *, require_markdown: bool = False) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        raise HTTPException(status_code=400, detail="OS path is required")
    if Path(normalized).is_absolute() or normalized.startswith("/"):
        raise HTTPException(status_code=400, detail="OS path must be relative")
    if ".." in normalized.split("/"):
        raise HTTPException(status_code=400, detail="OS path must not contain directory traversal")
    if require_markdown and Path(normalized).suffix.lower() not in _VALID_OS_EXTENSIONS:
        raise HTTPException(status_code=400, detail="OS file path must point to a Markdown file")
    return normalized


def _extract_review_checklist(body: str) -> dict:
    approved = re.search(r"^\s*[-*]\s+\[(?P<mark>[ xX])\]\s+Approved\s*$", body, re.MULTILINE)
    rejected = re.search(r"^\s*[-*]\s+\[(?P<mark>[ xX])\]\s+Rejected\s*$", body, re.MULTILINE)
    return {
        "hasApproved": approved is not None,
        "hasRejected": rejected is not None,
        "approvedChecked": bool(approved and approved.group("mark").lower() == "x"),
        "rejectedChecked": bool(rejected and rejected.group("mark").lower() == "x"),
    }


def _markdown_section(body: str, heading: str) -> str:
    lines = body.splitlines()
    marker = f"## {heading}"
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == marker)
    except StopIteration:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start + 1:end]).strip()


def _candidate_destination_from_body(body: str) -> str | None:
    candidate = _markdown_section(body, "Candidate Destination")
    match = _MARKDOWN_CODE_PATH_PATTERN.search(candidate)
    if not match:
        return None
    try:
        return _validate_os_relative_path(match.group(1), require_markdown=True)
    except HTTPException:
        return None


def _build_apply_hint(draft: dict, body: str, approval: str) -> dict:
    fm = draft.get("frontmatter") if isinstance(draft.get("frontmatter"), dict) else {}
    destination = _candidate_destination_from_body(body)
    if approval != "approved":
        return {
            "supported": False,
            "enabled": False,
            "target": destination,
            "reason": "Draft must be approved before it can be applied.",
        }
    if fm.get("source") != "import":
        return {
            "supported": False,
            "enabled": False,
            "target": destination,
            "reason": "Automatic apply supports only imported raw-inbox drafts.",
        }
    if fm.get("memory_level") != "session":
        return {
            "supported": False,
            "enabled": False,
            "target": destination,
            "reason": "Automatic apply supports only session-memory drafts.",
        }
    if not destination:
        return {
            "supported": False,
            "enabled": False,
            "target": None,
            "reason": "Draft has no machine-readable Candidate Destination.",
        }
    if not destination.startswith("05_Memory/Session/"):
        return {
            "supported": False,
            "enabled": False,
            "target": destination,
            "reason": "Automatic apply supports only targets under 05_Memory/Session/.",
        }
    return {
        "supported": True,
        "enabled": True,
        "target": destination,
        "reason": "Approved raw-inbox session draft can be applied through the SDK boundary.",
    }


def _build_approval_guard(draft: dict) -> dict:
    body = str(draft.get("body") or "")
    approval = str(draft.get("approval") or "unknown")
    checklist = _extract_review_checklist(body)
    checks: list[dict] = []

    if approval in {"pending", "approved"}:
        checks.append(_review_check("Draft state", "ok", f"Draft state is {approval}."))
    else:
        checks.append(_review_check("Draft state", "block", f"Draft state is {approval}."))

    has_both_boxes = bool(checklist.get("hasApproved")) and bool(checklist.get("hasRejected"))
    approved_checked = bool(checklist.get("approvedChecked"))
    rejected_checked = bool(checklist.get("rejectedChecked"))
    if not has_both_boxes:
        checks.append(_review_check("Approval checklist", "block", "Approved/Rejected checklist is incomplete."))
    elif approved_checked and rejected_checked:
        checks.append(_review_check("Approval checklist", "block", "Both decision boxes are checked."))
    elif rejected_checked and not approved_checked:
        checks.append(_review_check("Approval checklist", "block", "Rejected is already checked."))
    else:
        checks.append(_review_check("Approval checklist", "ok", "Approval checklist can be used for approval."))

    blocked = [check for check in checks if check["state"] == "block"]
    return {
        "blocked": bool(blocked),
        "checks": checks,
        "summary": "Approval blocked by review guard." if blocked else "Approval guard passed.",
    }


def _missing_tools(tool_names: set[str], required: set[str]) -> list[str]:
    return sorted(required - tool_names)


def _build_personal_os_status_payload(tools: list[dict]) -> dict:
    tool_names = sorted(str(tool.get("name", "")) for tool in tools if tool.get("name"))
    tool_set = set(tool_names)
    queue_tools = {"os_list_drafts", "os_view_draft"}
    review_tools = {"os_view_draft", "os_read_file", "os_draft_history"}
    context_tools = {"os_query_index", "os_read_file"}
    graph_tools = {"os_graph_index"}
    apply_tools = queue_tools
    capabilities = {
        "draftQueue": not _missing_tools(tool_set, queue_tools),
        "reviewPacket": not _missing_tools(tool_set, review_tools),
        "auditHistory": "os_draft_history" in tool_set,
        "contextBrowser": not _missing_tools(tool_set, context_tools),
        "graph": not _missing_tools(tool_set, graph_tools),
        "explicitApply": not _missing_tools(tool_set, apply_tools),
    }
    missing = {
        "draftQueue": _missing_tools(tool_set, queue_tools),
        "reviewPacket": _missing_tools(tool_set, review_tools),
        "contextBrowser": _missing_tools(tool_set, context_tools),
        "graph": _missing_tools(tool_set, graph_tools),
    }
    return {
        "status": "connected",
        "server": _PERSONAL_OS_SERVER,
        "tools": tool_names,
        "tools_count": len(tool_names),
        "draft_review": capabilities["draftQueue"],
        "capabilities": capabilities,
        "missing_tools": missing,
    }


def _count_value(counts: dict, key: str) -> int:
    try:
        return int(counts.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _diagnostic_check(check_id: str, label: str, state: Literal["ok", "warn", "block"], detail: str) -> dict:
    return {"id": check_id, "label": label, "state": state, "detail": detail}


def _format_disk_bytes(value: int) -> str:
    if value >= 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024 * 1024):.1f} GiB"
    return f"{value / (1024 * 1024):.0f} MiB"


def _build_storage_check() -> dict:
    try:
        path = Path(os.getenv("LEXA_DISK_CHECK_PATH") or Path.cwd()).resolve()
        usage = shutil.disk_usage(path)
    except Exception as exc:
        return _diagnostic_check("system-storage", "System storage", "warn", f"Disk space check unavailable: {exc}")

    free_text = _format_disk_bytes(int(usage.free))
    total_text = _format_disk_bytes(int(usage.total))
    if usage.free < _DISK_BLOCK_BYTES:
        return _diagnostic_check(
            "system-storage",
            "System storage",
            "block",
            f"Only {free_text} free on the Lexa drive ({total_text} total); free disk space before write-heavy work.",
        )
    if usage.free < _DISK_WARN_BYTES:
        return _diagnostic_check(
            "system-storage",
            "System storage",
            "warn",
            f"Low disk space: {free_text} free on the Lexa drive ({total_text} total); npm/build/log writes may fail.",
        )
    return _diagnostic_check("system-storage", "System storage", "ok", f"{free_text} free on the Lexa drive.")


def _build_personal_os_diagnostics(status: dict, queue: dict) -> dict:
    raw_counts = queue.get("counts") if isinstance(queue.get("counts"), dict) else {}
    counts = {
        "total": _count_value(raw_counts, "total"),
        "pending": _count_value(raw_counts, "pending"),
        "approved": _count_value(raw_counts, "approved"),
        "rejected": _count_value(raw_counts, "rejected"),
        "conflict": _count_value(raw_counts, "conflict"),
        "missing": _count_value(raw_counts, "missing"),
        "invalid": _count_value(raw_counts, "invalid"),
    }
    capabilities = status.get("capabilities") if isinstance(status.get("capabilities"), dict) else {}
    missing_tools = status.get("missing_tools") if isinstance(status.get("missing_tools"), dict) else {}
    ready_caps = [key for key in _CAPABILITY_KEYS if capabilities.get(key)]
    missing_cap_names = [key for key in _CAPABILITY_KEYS if not capabilities.get(key)]
    missing_tool_names = sorted({
        tool
        for values in missing_tools.values()
        if isinstance(values, list)
        for tool in values
        if isinstance(tool, str)
    })

    checks = [
        _diagnostic_check("mcp", "MCP connection", "ok", f"{status.get('server', _PERSONAL_OS_SERVER)} connected."),
        _build_storage_check(),
    ]
    if missing_cap_names:
        detail = "Missing capabilities: " + ", ".join(missing_cap_names)
        if missing_tool_names:
            detail += ". Missing tools: " + ", ".join(missing_tool_names)
        checks.append(_diagnostic_check("capabilities", "Capabilities", "block", detail))
    else:
        checks.append(_diagnostic_check("capabilities", "Capabilities", "ok", f"{len(ready_caps)}/{len(_CAPABILITY_KEYS)} capabilities ready."))

    if counts["invalid"]:
        checks.append(_diagnostic_check("draft-validity", "Draft validity", "block", f"{counts['invalid']} invalid draft(s) or queue error(s)."))
    else:
        checks.append(_diagnostic_check("draft-validity", "Draft validity", "ok", "No invalid non-smoke drafts."))

    if counts["pending"]:
        checks.append(_diagnostic_check("pending-drafts", "Pending drafts", "warn", f"{counts['pending']} draft(s) still need human review."))
    else:
        checks.append(_diagnostic_check("pending-drafts", "Pending drafts", "ok", "Review queue is free."))

    checks.append(_diagnostic_check("decisions", "Recorded decisions", "ok", f"{counts['approved']} approved and {counts['rejected']} rejected draft(s)."))

    blocked_checks = [check for check in checks if check["state"] == "block"]
    warning_checks = [check for check in checks if check["state"] == "warn"]
    blocked = len(blocked_checks)
    warnings = len(warning_checks)
    if blocked:
        state = "blocked"
        summary = "Personal OS integration has blocking issues."
        if any(check["id"] == "system-storage" for check in blocked_checks):
            next_action = "Free disk space before write-heavy Lexa or Personal OS work."
        else:
            next_action = "Fix missing capabilities or invalid drafts before relying on the cockpit."
    elif warnings:
        state = "attention"
        summary = "Personal OS integration is connected but needs review attention."
        if counts["pending"]:
            next_action = "Review pending drafts through the cockpit."
        elif any(check["id"] == "system-storage" for check in warning_checks):
            next_action = "Free disk space or avoid write-heavy commands before continuing heavy work."
        else:
            next_action = "Inspect warning diagnostics before continuing."
    else:
        state = "ready"
        summary = "Personal OS integration is connected and the review queue is clear."
        next_action = "Continue with context browsing, Context Map review, or new controlled draft intake."

    return {
        "ok": blocked == 0,
        "state": state,
        "summary": summary,
        "checks": checks,
        "counts": counts,
        "status": status,
        "nextAction": next_action,
    }


def _infer_target_from_sdk_draft_path(draft_path: str) -> str | None:
    filename = Path(draft_path.replace("\\", "/")).name
    match = _SDK_DRAFT_NAME_PATTERN.match(filename)
    if not match:
        return None
    try:
        return _validate_os_relative_path(match.group("safe").replace("__", "/") + ".md", require_markdown=True)
    except HTTPException:
        return None


def _infer_target_from_frontmatter(fm: dict) -> str | None:
    for key in ("target_file", "targetFile", "target"):
        value = fm.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            return _validate_os_relative_path(value, require_markdown=True)
        except HTTPException:
            return None
    return None


def _body_preview(value: object, limit: int = 1200) -> str:
    text = str(value or "")
    return text if len(text) <= limit else f"{text[:limit]}\n\n[truncated]"


def _frontmatter_summary(payload: dict) -> dict:
    fm = payload.get("frontmatter") if isinstance(payload.get("frontmatter"), dict) else {}
    return {
        "path": payload.get("path"),
        "title": fm.get("title"),
        "type": fm.get("type"),
        "status": fm.get("status"),
        "memory_level": fm.get("memory_level"),
        "updated": fm.get("updated"),
        "bodyPreview": _body_preview(payload.get("body")),
    }


def _context_pack_file(payload: dict, body_chars: int) -> dict:
    fm = payload.get("frontmatter") if isinstance(payload.get("frontmatter"), dict) else {}
    body = str(payload.get("body") or "")
    return {
        "path": payload.get("path"),
        "title": fm.get("title") or payload.get("path"),
        "type": fm.get("type"),
        "status": fm.get("status"),
        "memory_level": fm.get("memory_level"),
        "source": fm.get("source"),
        "confidence": fm.get("confidence"),
        "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [],
        "related": fm.get("related") if isinstance(fm.get("related"), list) else [],
        "bodyPreview": _body_preview(body, body_chars),
        "truncated": len(body) > body_chars,
    }


def _is_smoke_context(*values: object) -> bool:
    haystack = "\n".join(str(value or "") for value in values).lower()
    return "smoke" in haystack or "smoke-test" in haystack or "smoke_test" in haystack


def _list_value(value: object, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()][:limit]


def _draft_search_text(draft: dict) -> str:
    fields = [
        draft.get("title"),
        draft.get("path"),
        draft.get("approval"),
        draft.get("source"),
        draft.get("memory_level"),
    ]
    fields.extend(_list_value(draft.get("tags"), 16))
    return "\n".join(str(value or "").lower() for value in fields)


def _compact_code_loop_draft(draft: dict) -> dict:
    return {
        "title": draft.get("title") or "Untitled",
        "path": draft.get("path"),
        "approval": draft.get("approval"),
        "memory_level": draft.get("memory_level"),
        "source": draft.get("source"),
        "tags": _list_value(draft.get("tags"), 8),
    }


def _code_loop_draft_rank(draft: dict) -> int:
    approval = str(draft.get("approval") or "").lower()
    if approval in {"invalid", "conflict", "missing"}:
        return 0
    if approval in {"pending", "review"}:
        return 1
    if approval == "approved":
        return 2
    if approval == "rejected":
        return 3
    return 4


def _select_code_loop_drafts(queue: dict, limit: int = 8) -> list[dict]:
    drafts = queue.get("drafts") if isinstance(queue.get("drafts"), list) else []
    terms = ("lexa", "personal-os", "cockpit", "mcp", "sdk")
    matches = [
        (_code_loop_draft_rank(draft), index, _compact_code_loop_draft(draft))
        for index, draft in enumerate(drafts)
        if isinstance(draft, dict) and any(term in _draft_search_text(draft) for term in terms)
    ]
    return [entry[2] for entry in sorted(matches, key=lambda entry: (entry[0], entry[1]))[:limit]]


def _compact_graph_summary(payload: dict) -> dict:
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    file_nodes = [
        {
            "path": node.get("path") or node.get("id"),
            "label": node.get("label") or node.get("path") or node.get("id"),
            "memory_level": node.get("memory_level"),
            "type": node.get("type"),
        }
        for node in nodes
        if isinstance(node, dict) and node.get("kind") == "file"
    ][:12]
    return {
        "ok": payload.get("ok", True),
        "areaPath": payload.get("areaPath"),
        "counts": payload.get("counts") if isinstance(payload.get("counts"), dict) else {},
        "files": file_nodes,
        "errors": [
            {
                "path": error.get("path"),
                "error": _body_preview(error.get("error"), 360),
            }
            for error in errors[:5]
            if isinstance(error, dict)
        ],
        "truncated": bool(payload.get("truncated")),
    }


async def _build_context_pack_payload(
    *,
    area_path: str,
    tag: str | None,
    max_files: int,
    body_chars: int,
    include_graph: bool,
    hide_smoke: bool,
    agent_name: str,
    reason_prefix: str,
) -> dict:
    normalized_area = _validate_os_relative_path(area_path)
    normalized_tag = _normalize_tag_filter(tag)

    query_args = {
        "areaPath": normalized_area,
        "maxMatches": max(max_files * 3, 12),
        "agentName": agent_name,
        "reason": f"{reason_prefix} query",
    }
    if normalized_tag:
        query_args["tag"] = normalized_tag
    query_payload = await _call_personal_os_tool("os_query_index", query_args)

    candidate_paths: list[str] = []
    matches = query_payload.get("matches") if isinstance(query_payload.get("matches"), list) else None
    if matches is not None:
        for match in matches:
            if not isinstance(match, dict) or not isinstance(match.get("path"), str):
                continue
            if hide_smoke and _is_smoke_context(match.get("path"), match.get("title"), match.get("tags")):
                continue
            try:
                candidate_paths.append(_validate_os_relative_path(match["path"], require_markdown=True))
            except HTTPException:
                continue
    elif isinstance(query_payload.get("path"), str):
        if not hide_smoke or not _is_smoke_context(query_payload.get("path"), query_payload.get("frontmatter")):
            candidate_paths.append(_validate_os_relative_path(query_payload["path"], require_markdown=True))

    seen_paths: set[str] = set()
    files: list[dict] = []
    errors: list[dict] = []
    for candidate_path in candidate_paths:
        if candidate_path in seen_paths:
            continue
        seen_paths.add(candidate_path)
        if len(files) >= max_files:
            break
        try:
            file_payload = await _call_personal_os_tool("os_read_file", {
                "filepath": candidate_path,
                "agentName": agent_name,
                "reason": f"{reason_prefix} file read",
            })
            files.append(_context_pack_file(file_payload, body_chars))
        except HTTPException as exc:
            errors.append({"path": candidate_path, "error": str(exc.detail)})

    graph = None
    if include_graph:
        try:
            graph_payload = await _call_personal_os_tool("os_graph_index", {
                "areaPath": normalized_area,
                "maxFiles": max(40, max_files * 12),
                "includeTags": True,
                "hideSmoke": hide_smoke,
                "agentName": agent_name,
                "reason": f"{reason_prefix} context map summary",
            })
            graph = _compact_graph_summary(graph_payload)
        except HTTPException as exc:
            graph = {"ok": False, "error": str(exc.detail)}

    return {
        "ok": True,
        "query": {
            "areaPath": normalized_area,
            "tag": normalized_tag,
            "candidateCount": len(candidate_paths),
            "includedCount": len(files),
            "maxFiles": max_files,
            "bodyChars": body_chars,
            "hideSmoke": hide_smoke,
        },
        "files": files,
        "graph": graph,
        "errors": errors,
        "truncated": len(seen_paths) < len(candidate_paths),
    }


def _format_code_loop_prompt(payload: dict) -> str:
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    raw_status = payload.get("rawInbox") if isinstance(payload.get("rawInbox"), dict) else {}
    context_pack = payload.get("contextPack") if isinstance(payload.get("contextPack"), dict) else {}
    drafts_payload = payload.get("drafts") if isinstance(payload.get("drafts"), dict) else {}
    counts = diagnostics.get("counts") if isinstance(diagnostics.get("counts"), dict) else {}
    context_files = context_pack.get("files") if isinstance(context_pack.get("files"), list) else []
    drafts = drafts_payload.get("items") if isinstance(drafts_payload.get("items"), list) else []
    processors = raw_status.get("processors") if isinstance(raw_status.get("processors"), list) else []
    failure_state = raw_status.get("failureState") if isinstance(raw_status.get("failureState"), dict) else {}

    processor_summary = ", ".join(
        f"{entry.get('name', 'unknown')}={entry.get('status', 'unknown')}"
        for entry in processors[:4]
        if isinstance(entry, dict)
    ) or "unknown"
    graph = context_pack.get("graph") if isinstance(context_pack.get("graph"), dict) else {}
    graph_counts = graph.get("counts") if isinstance(graph.get("counts"), dict) else {}
    graph_errors = graph.get("errors") if isinstance(graph.get("errors"), list) else []
    graph_summary = (
        f"ok={bool(graph.get('ok', True))}, files={graph_counts.get('files', 0)}, "
        f"edges={graph_counts.get('edges', 0)}, errors={graph_counts.get('errors', len(graph_errors))}"
    )
    graph_error_summary = "\n".join(
        f"- {entry.get('path', '-')}: {str(entry.get('error') or '').splitlines()[0][:180]}"
        for entry in graph_errors[:3]
        if isinstance(entry, dict)
    ) or "- No Context Map errors reported in compact summary."
    context_summary = "\n\n".join(
        "\n".join([
            f"## {file.get('title') or file.get('path') or 'OS file'}",
            f"Path: {file.get('path', '-')}",
            f"Tags: {', '.join(_list_value(file.get('tags'), 8)) or '-'}",
            str(file.get("bodyPreview") or "").strip()[:900],
        ]).strip()
        for file in context_files[:5]
        if isinstance(file, dict)
    ) or "No OS context files were included."
    draft_summary = "\n".join(
        f"- {draft.get('title', 'Untitled')} [{draft.get('approval', 'unknown')}]: {draft.get('path', '-')}"
        for draft in drafts[:8]
        if isinstance(draft, dict)
    ) or "- No Lexa-related drafts found."

    return "\n".join([
        "Du bist Lexa und nutzt das Personal OS als read-only Arbeitsgedaechtnis fuer Lexa-Code-Verbesserungen.",
        "",
        "Sicherheitsgrenze:",
        "- Das OS ist Quelle und Review-System, nicht direkter Schreibkanal.",
        "- Keine Stable-Memory- oder Projekt-OS-Dateien ohne Draft/Approval veraendern.",
        "- Fuer Codeaenderungen zuerst das Lexa-Repo inspizieren, klein schneiden und danach Tests ausfuehren.",
        "",
        "Personal OS Status:",
        f"- State: {diagnostics.get('state', 'unknown')}",
        f"- Summary: {diagnostics.get('summary', '-')}",
        f"- Drafts: pending={counts.get('pending', 0)}, approved={counts.get('approved', 0)}, rejected={counts.get('rejected', 0)}, invalid={counts.get('invalid', 0)}",
        f"- Next: {diagnostics.get('nextAction', '-')}",
        "",
        "Raw Inbox Worker:",
        f"- OK: {bool(raw_status.get('ok'))}",
        f"- Processors: {processor_summary}",
        f"- Failed files: {failure_state.get('failed', 0)}",
        "",
        "Context Map Health:",
        f"- {graph_summary}",
        graph_error_summary,
        "",
        "Relevant Draft Decisions:",
        draft_summary,
        "",
        "Relevant OS Context:",
        context_summary,
        "",
        "Aufgabe:",
        "1. Leite aus diesem OS-Kontext den naechsten kleinen Lexa-Code-Verbesserungsschritt ab.",
        "2. Nenne die konkrete Evidenz aus dem OS, auf die du dich stuetzt.",
        "3. Inspiziere das Lexa-Repo lokal und baue den kleinsten sicheren Patch.",
        "4. Fuehre passende gezielte Tests aus; bei UI/Runtime-Aenderungen auch eine passende Smoke-Pruefung.",
        "5. Dokumentiere relevante Ergebnisse im bestehenden OS-Draft, nicht in stabiler Memory.",
        "6. Stoppe nur, wenn eine menschliche Entscheidung wirklich noetig ist.",
        "",
        "Qualitaetsstandard:",
        "- Keine billigen Demo-Funktionen oder kosmetischen Scheinfunktionen.",
        "- Stabilitaet, UX, Design/CSS, Voice, Personal-OS-Integration und Tests zaehlen mehr als Show.",
        "- Orientiere dich an professionellen Standards moderner Assistenten.",
    ]).strip()


async def _build_lexa_code_loop_payload(
    *,
    area_path: str,
    tag: str | None,
    max_files: int,
    body_chars: int,
    include_graph: bool,
    hide_smoke: bool,
    agent_name: str,
    reason_prefix: str,
) -> dict:
    tools = await _ensure_personal_os_connected()
    status = _build_personal_os_status_payload(tools)
    queue = await _call_personal_os_tool("os_list_drafts", {
        "hideSmoke": hide_smoke,
        "maxDrafts": 200,
        "agentName": agent_name,
        "reason": f"{reason_prefix} draft queue read",
    })
    diagnostics = _build_personal_os_diagnostics(status, queue)
    try:
        raw_status = await _run_raw_inbox_worker_status()
    except HTTPException as exc:
        raw_status = {"ok": False, "error": str(exc.detail), "processors": [], "failureState": {"failed": 0, "failures": []}}

    context_pack = await _build_context_pack_payload(
        area_path=area_path,
        tag=tag,
        max_files=max_files,
        body_chars=body_chars,
        include_graph=include_graph,
        hide_smoke=hide_smoke,
        agent_name=agent_name,
        reason_prefix=f"{reason_prefix} context pack",
    )
    payload = {
        "ok": True,
        "topic": "lexa-code-improvement",
        "diagnostics": diagnostics,
        "rawInbox": raw_status,
        "drafts": {
            "query": "lexa personal-os cockpit mcp sdk",
            "counts": queue.get("counts") if isinstance(queue.get("counts"), dict) else {},
            "total": len(queue.get("drafts") if isinstance(queue.get("drafts"), list) else []),
            "items": _select_code_loop_drafts(queue),
        },
        "contextPack": context_pack,
    }
    payload["prompt"] = _format_code_loop_prompt(payload)
    return payload


def _diff_bodies(before: str, after: str, *, limit: int = 160) -> dict:
    lines = list(difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="current",
        tofile="draft",
        lineterm="",
    ))
    truncated = len(lines) > limit
    if truncated:
        lines = lines[:limit] + [f"... truncated {len(lines) - limit} diff lines"]
    return {
        "lines": lines,
        "truncated": truncated,
        "changed": before != after,
        "lineCount": len(lines),
    }


def _review_check(label: str, state: Literal["ok", "warn", "block"], detail: str) -> dict:
    return {"label": label, "state": state, "detail": detail}


def _build_review_assist(
    draft: dict,
    checklist: dict,
    related: list[dict],
    history: dict,
    target_candidate: str | None,
    target_source: str | None,
    target: dict | None,
    diff: dict | None,
) -> dict:
    """Build deterministic review hints without making an approval decision."""
    checks: list[dict] = []
    approval = str(draft.get("approval") or "unknown")
    fm = draft.get("frontmatter") if isinstance(draft.get("frontmatter"), dict) else {}
    confidence = str(fm.get("confidence") or "unknown").lower()

    if approval == "pending":
        checks.append(_review_check("Draft state", "ok", "Draft is still pending human decision."))
    elif approval in {"approved", "rejected"}:
        checks.append(_review_check("Draft state", "warn", f"Draft is already marked {approval}."))
    else:
        checks.append(_review_check("Draft state", "block", f"Draft state is {approval}."))

    has_both_boxes = bool(checklist.get("hasApproved")) and bool(checklist.get("hasRejected"))
    approved_checked = bool(checklist.get("approvedChecked"))
    rejected_checked = bool(checklist.get("rejectedChecked"))
    if not has_both_boxes:
        checks.append(_review_check("Approval checklist", "block", "Approved/Rejected checklist is incomplete."))
    elif approved_checked and rejected_checked:
        checks.append(_review_check("Approval checklist", "block", "Both decision boxes are checked."))
    elif approved_checked or rejected_checked:
        checks.append(_review_check("Approval checklist", "warn", "A decision box is already checked in the draft body."))
    else:
        checks.append(_review_check("Approval checklist", "ok", "Both decision boxes are present and unchecked."))

    if confidence in {"high", "medium"}:
        checks.append(_review_check("Confidence", "ok", f"Draft declares {confidence} confidence."))
    else:
        checks.append(_review_check("Confidence", "warn", "Draft confidence is missing or low."))

    readable_related = [item for item in related if not item.get("error")]
    if readable_related:
        checks.append(_review_check("Related context", "ok", f"{len(readable_related)} related file(s) loaded."))
    else:
        checks.append(_review_check("Related context", "warn", "No readable related context was loaded."))

    history_events = history.get("events") if isinstance(history.get("events"), list) else []
    if history.get("ok") and history_events:
        checks.append(_review_check("Audit history", "ok", f"{len(history_events)} event(s) found."))
    else:
        checks.append(_review_check("Audit history", "warn", "No matching audit events were found."))

    if target_candidate:
        if target and target.get("error"):
            checks.append(_review_check("Target comparison", "warn", f"Could not read target {target_candidate}."))
        elif diff:
            detail = "Body diff available." if diff.get("changed") else "Target body and draft body are identical."
            checks.append(_review_check("Target comparison", "ok", detail))
        elif target_source == "frontmatter":
            checks.append(_review_check("Target comparison", "ok", "Target file loaded from draft metadata; review proposed change manually."))
        else:
            checks.append(_review_check("Target comparison", "warn", "Target was inferred but no diff was produced."))
    else:
        checks.append(_review_check("Target comparison", "ok", "No SDK target inferred; review as standalone draft."))

    blocked = sum(1 for check in checks if check["state"] == "block")
    warnings = sum(1 for check in checks if check["state"] == "warn")
    if blocked:
        status = "blocked"
        summary = "Fix the blocking review checks before approving or rejecting."
    elif warnings:
        status = "attention"
        summary = "Review flagged items that need human attention before a decision."
    else:
        status = "ready"
        summary = "No deterministic review blockers found. Human approval is still required."

    return {
        "status": status,
        "summary": summary,
        "blocked": blocked,
        "warnings": warnings,
        "checks": checks,
        "nextAction": "Inspect the draft, history, related context, and diff, then choose Approve or Reject explicitly.",
    }


async def _build_draft_review_payload(draft_path: str, *, agent_name: str, reason_prefix: str) -> dict:
    draft = await _call_personal_os_tool("os_view_draft", {
        "draftPath": draft_path,
        "agentName": agent_name,
        "reason": f"{reason_prefix} review packet",
    })

    fm = draft.get("frontmatter") if isinstance(draft.get("frontmatter"), dict) else {}
    body = str(draft.get("body") or "")
    approval = str(draft.get("approval") or "unknown")
    related_paths = []
    for value in fm.get("related") if isinstance(fm.get("related"), list) else []:
        if not isinstance(value, str):
            continue
        try:
            related_paths.append(_validate_os_relative_path(value, require_markdown=True))
        except HTTPException:
            continue
        if len(related_paths) >= 5:
            break

    related = []
    for related_path in related_paths:
        try:
            related_payload = await _call_personal_os_tool("os_read_file", {
                "filepath": related_path,
                "agentName": agent_name,
                "reason": f"{reason_prefix} related context read",
            })
            related.append(_frontmatter_summary(related_payload))
        except HTTPException as exc:
            related.append({"path": related_path, "error": str(exc.detail)})

    frontmatter_target = _infer_target_from_frontmatter(fm)
    sdk_target = _infer_target_from_sdk_draft_path(draft_path)
    inferred_target = frontmatter_target or sdk_target
    target_source = "frontmatter" if frontmatter_target else ("sdk-draft-path" if sdk_target else None)
    target = None
    diff = None
    if inferred_target:
        try:
            target_payload = await _call_personal_os_tool("os_read_file", {
                "filepath": inferred_target,
                "agentName": agent_name,
                "reason": f"{reason_prefix} target comparison read",
            })
            target = _frontmatter_summary(target_payload)
            if target_source == "sdk-draft-path":
                diff = _diff_bodies(str(target_payload.get("body") or ""), body)
        except HTTPException as exc:
            target = {"path": inferred_target, "error": str(exc.detail)}

    try:
        history = await _call_personal_os_tool("os_draft_history", {
            "draftPath": draft_path,
            "maxEvents": 50,
            "agentName": agent_name,
            "reason": f"{reason_prefix} history read",
        })
    except HTTPException as exc:
        history = {"ok": False, "events": [], "error": str(exc.detail)}

    checklist = _extract_review_checklist(body)
    apply_hint = _build_apply_hint(draft, body, approval)
    assist = _build_review_assist(
        draft,
        checklist,
        related,
        history,
        inferred_target,
        target_source,
        target,
        diff,
    )

    return {
        "ok": True,
        "draft": draft,
        "checklist": checklist,
        "targetCandidate": inferred_target,
        "targetSource": target_source,
        "target": target,
        "diff": diff,
        "related": related,
        "history": history,
        "applyHint": apply_hint,
        "assist": assist,
        "reviewHints": {
            "approval": draft.get("approval"),
            "confidence": fm.get("confidence"),
            "relatedCount": len(related),
            "historyCount": len(history.get("events", [])) if isinstance(history.get("events"), list) else 0,
            "hasTargetComparison": diff is not None,
            "assistStatus": assist["status"],
            "canApply": apply_hint["enabled"],
        },
    }


async def _run_draft_decision_cli(req: DraftDecisionRequest) -> dict:
    draft_path = _validate_draft_path(req.draftPath)
    os_root = _personal_os_root()
    sdk_dir = os_root / "00_System" / "SDK" / "os-sdk"
    if not sdk_dir.exists():
        raise HTTPException(status_code=502, detail=f"Personal OS SDK not found: {sdk_dir}")

    npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"
    script = f"draft:{req.decision}"
    process = await asyncio.create_subprocess_exec(
        npm_cmd,
        "run",
        script,
        "--",
        draft_path,
        "--agent",
        req.agentName,
        "--reason",
        req.reason,
        cwd=str(sdk_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=MCP_CALL_TIMEOUT)
    except asyncio.TimeoutError as exc:
        process.kill()
        raise HTTPException(status_code=504, detail="Draft decision timed out") from exc

    out_text = stdout.decode("utf-8", errors="replace").strip()
    err_text = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise HTTPException(status_code=502, detail=err_text or out_text or "Draft decision failed")

    try:
        payload = json.loads(out_text)
    except json.JSONDecodeError:
        payload = {"ok": True, "stdout": out_text}
    if not isinstance(payload, dict):
        payload = {"ok": True, "result": payload}
    return payload


async def _ensure_approval_guard(req: DraftDecisionRequest, draft_path: str) -> dict:
    if req.decision != "approve" or req.force:
        return {"blocked": False, "checks": [], "summary": "Approval guard skipped."}

    draft = await _call_personal_os_tool("os_view_draft", {
        "draftPath": draft_path,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS approval guard read",
    })
    guard = _build_approval_guard(draft)
    if guard["blocked"]:
        raise HTTPException(status_code=409, detail={
            "message": "Approval blocked by Review Assist guard. Use an explicit override only after human review.",
            "guard": guard,
        })
    return guard


async def _run_draft_apply_cli(req: DraftApplyRequest) -> dict:
    draft_path = _validate_draft_path(req.draftPath)
    os_root = _personal_os_root()
    sdk_dir = os_root / "00_System" / "SDK" / "os-sdk"
    if not sdk_dir.exists():
        raise HTTPException(status_code=502, detail=f"Personal OS SDK not found: {sdk_dir}")

    npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"
    process = await asyncio.create_subprocess_exec(
        npm_cmd,
        "run",
        "draft:apply",
        "--",
        draft_path,
        "--agent",
        req.agentName,
        "--reason",
        req.reason,
        cwd=str(sdk_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=MCP_CALL_TIMEOUT)
    except asyncio.TimeoutError as exc:
        process.kill()
        raise HTTPException(status_code=504, detail="Draft apply timed out") from exc

    out_text = stdout.decode("utf-8", errors="replace").strip()
    err_text = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise HTTPException(status_code=502, detail=err_text or out_text or "Draft apply failed")

    try:
        payload = json.loads(out_text)
    except json.JSONDecodeError:
        payload = {"ok": True, "stdout": out_text}
    if not isinstance(payload, dict):
        payload = {"ok": True, "result": payload}
    return payload


@router.get("/query")
async def query_os(
    areaPath: str = Query(default=".", min_length=1, max_length=300),
    tag: str | None = Query(default=None, max_length=80),
    maxMatches: int = Query(default=50, ge=1, le=200),
):
    """Read an OS area index or search machine-readable files by exact tag."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    normalized_area = _validate_os_relative_path(areaPath)
    normalized_tag = _normalize_tag_filter(tag)

    audit_log("personal_os", "query", f"area={normalized_area} tag={normalized_tag or ''}")
    arguments = {
        "areaPath": normalized_area,
        "maxMatches": maxMatches,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS context query",
    }
    if normalized_tag:
        arguments["tag"] = normalized_tag
    return await _call_personal_os_tool("os_query_index", arguments)


@router.get("/files/read")
async def read_os_file(filepath: str = Query(..., min_length=1, max_length=300)):
    """Read one machine-readable Personal OS Markdown file through MCP."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    normalized = _validate_os_relative_path(filepath, require_markdown=True)
    audit_log("personal_os", "file_read", f"path={normalized}")
    return await _call_personal_os_tool("os_read_file", {
        "filepath": normalized,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS file read",
    })


@router.get("/graph")
async def graph_os(
    areaPath: str = Query(default=".", min_length=1, max_length=300),
    maxFiles: int = Query(default=120, ge=1, le=400),
    includeTags: bool = Query(default=True),
    hideSmoke: bool = Query(default=True),
):
    """Build a read-only Personal OS graph through the MCP graph index."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    normalized_area = _validate_os_relative_path(areaPath)
    audit_log("personal_os", "graph", f"area={normalized_area} maxFiles={maxFiles}")
    return await _call_personal_os_tool("os_graph_index", {
        "areaPath": normalized_area,
        "maxFiles": maxFiles,
        "includeTags": includeTags,
        "hideSmoke": hideSmoke,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS graph read",
    })


@router.get("/context-pack")
async def context_pack_os(
    areaPath: str = Query(default=".", min_length=1, max_length=300),
    tag: str | None = Query(default=None, max_length=80),
    maxFiles: int = Query(default=5, ge=1, le=12),
    bodyChars: int = Query(default=700, ge=160, le=2000),
    includeGraph: bool = Query(default=True),
    hideSmoke: bool = Query(default=True),
):
    """Build a compact read-only context packet from OS query results."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    audit_log("personal_os", "context_pack", f"area={areaPath} tag={(tag or '').strip()}")
    return await _build_context_pack_payload(
        area_path=areaPath,
        tag=tag,
        max_files=maxFiles,
        body_chars=bodyChars,
        include_graph=includeGraph,
        hide_smoke=hideSmoke,
        agent_name="LexaPersonalOS",
        reason_prefix="Lexa Personal OS context pack",
    )


@router.get("/lexa-code-loop")
async def lexa_code_loop_os(
    areaPath: str = Query(default="00_System", min_length=1, max_length=300),
    tag: str | None = Query(default="lexa", max_length=80),
    maxFiles: int = Query(default=5, ge=1, le=8),
    bodyChars: int = Query(default=650, ge=160, le=1400),
    includeGraph: bool = Query(default=True),
    hideSmoke: bool = Query(default=True),
):
    """Build a read-only OS briefing prompt for the next Lexa code improvement."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    audit_log("personal_os", "lexa_code_loop", f"area={areaPath} tag={(tag or '').strip()}")
    return await _build_lexa_code_loop_payload(
        area_path=areaPath,
        tag=tag,
        max_files=maxFiles,
        body_chars=bodyChars,
        include_graph=includeGraph,
        hide_smoke=hideSmoke,
        agent_name="LexaPersonalOS",
        reason_prefix="Lexa Personal OS code loop",
    )


@router.get("/status")
async def personal_os_status():
    """Return Personal OS MCP connection and tool status for the cockpit."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    tools = await _ensure_personal_os_connected()
    return _build_personal_os_status_payload(tools)


@router.get("/diagnostics")
async def personal_os_diagnostics():
    """Return a compact Personal OS readiness diagnostic for startup and cockpit UI."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    tools = await _ensure_personal_os_connected()
    status = _build_personal_os_status_payload(tools)
    audit_log("personal_os", "diagnostics", "readiness check")
    queue = await _call_personal_os_tool("os_list_drafts", {
        "hideSmoke": True,
        "maxDrafts": 200,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS diagnostics queue read",
    })
    return _build_personal_os_diagnostics(status, queue)


@router.get("/drafts")
async def list_drafts(
    approval: str | None = Query(default="pending", max_length=20),
    hideSmoke: bool = Query(default=True),
    maxDrafts: int = Query(default=50, ge=1, le=200),
):
    """List Personal OS drafts through the MCP review queue."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    approvals: list[str] | None = None
    if approval and approval != "all":
        if approval not in _DRAFT_APPROVALS:
            raise HTTPException(status_code=400, detail="Invalid draft approval filter")
        approvals = [approval]

    audit_log("personal_os", "drafts_list", f"approval={approval or 'all'} hideSmoke={hideSmoke}")
    arguments = {
        "hideSmoke": hideSmoke,
        "maxDrafts": maxDrafts,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS draft queue read",
    }
    if approvals is not None:
        arguments["approvals"] = approvals
    return await _call_personal_os_tool("os_list_drafts", arguments)


@router.get("/drafts/view")
async def view_draft(draftPath: str = Query(..., min_length=1, max_length=300)):
    """View one Personal OS draft through the read-only MCP review tool."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    draft_path = _validate_draft_path(draftPath)
    audit_log("personal_os", "draft_view", f"path={draft_path}")
    return await _call_personal_os_tool("os_view_draft", {
        "draftPath": draft_path,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS draft view",
    })


@router.get("/drafts/review")
async def review_draft(draftPath: str = Query(..., min_length=1, max_length=300)):
    """Build a read-only review packet for one draft and nearby context."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    draft_path = _validate_draft_path(draftPath)
    audit_log("personal_os", "draft_review_packet", f"path={draft_path}")
    return await _build_draft_review_payload(
        draft_path,
        agent_name="LexaPersonalOS",
        reason_prefix="Lexa Personal OS draft",
    )


@router.post("/drafts/decision")
async def decide_draft(req: DraftDecisionRequest):
    """Mark a draft approved or rejected via the Personal OS SDK CLI."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    draft_path = _validate_draft_path(req.draftPath)
    audit_log("personal_os", f"draft_{req.decision}", f"path={draft_path}")
    await _ensure_approval_guard(req, draft_path)
    return await _run_draft_decision_cli(req)


@router.post("/drafts/apply")
async def apply_draft(req: DraftApplyRequest):
    """Apply an approved draft via the Personal OS SDK CLI boundary."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    draft_path = _validate_draft_path(req.draftPath)
    audit_log("personal_os", "draft_apply", f"path={draft_path}")
    return await _run_draft_apply_cli(req)


@router.post("/raw-inbox/submit")
async def raw_inbox_submit(req: RawInboxSubmitRequest):
    """Submit untrusted raw text, then run the MCP worker to create a review draft."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    raw = await _write_raw_inbox_file(req)
    worker = await _run_raw_inbox_worker(str(raw["filename"]), req.processor)
    return {
        "ok": bool(worker.get("ok")),
        "raw": raw,
        "worker": worker,
        "drafts": worker.get("drafts") if isinstance(worker.get("drafts"), list) else [],
    }


@router.get("/raw-inbox/status")
async def raw_inbox_status():
    """Return local raw-inbox worker readiness without writing OS files."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    audit_log("personal_os", "raw_inbox_status", "worker readiness check")
    return await _run_raw_inbox_worker_status()


@router.post("/raw-inbox/extract", response_model=RawInboxExtractResponse)
async def raw_inbox_extract(req: RawInboxExtractRequest):
    """Extract summary and tags without using normal chat history or tools."""
    if not check_rate_limit("chat"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    audit_log("personal_os", "raw_inbox_extract", f"SOURCE={req.sourcePath[:120]}")

    try:
        from backend.ai_engine import _chat_with_selected_provider, _get_selected_model_meta

        selected_model = _get_selected_model_meta()
        result = await asyncio.to_thread(
            _chat_with_selected_provider,
            _build_messages(req),
            selected_model,
            None,
        )
    except Exception as exc:
        logger.exception("Personal OS raw inbox extraction failed")
        raise HTTPException(status_code=502, detail="Lexa extraction failed") from exc

    if not result or result.get("type") != "text":
        raise HTTPException(status_code=502, detail="Lexa extraction did not return text")

    try:
        summary, tags = _parse_extraction(str(result.get("content", "")))
    except ValueError as exc:
        logger.warning("Personal OS extraction returned invalid JSON: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RawInboxExtractResponse(
        status="ok",
        summary=summary,
        tags=tags,
        provider=selected_model.get("provider"),
        model=selected_model.get("model"),
    )
