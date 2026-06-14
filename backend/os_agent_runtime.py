"""Lexa OS agent runtime.

Lexa is the control plane, Personal OS is the context and approval layer,
and worker agents such as Hermes execute bounded tasks through this runtime.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.hermes_adapter import (
    HERMES_WORKSPACE_ROOT,
    PERSONAL_OS_ROOT,
    PROJECT_ROOT,
    get_hermes_status,
    run_hermes_task,
)
from backend.lexa_voice import LEXA_WORKER_VOICE_RULES

logger = logging.getLogger(__name__)

TASK_STORE_ROOT = HERMES_WORKSPACE_ROOT / "os_agent_tasks"
_MAX_STORED_TASKS = 200
_MAX_STORED_TEXT = 16000
_MAX_REVIEW_OUTPUT = 2000
_LOCK = threading.RLock()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lexa-os-agent")
# Cache the os-sdk build outcome so that a missing dist/ does not trigger a
# blocking npm build (up to 60s) on every review-draft creation. Guarded by
# _LOCK; None = not yet attempted, True/False = last known build state.
_SDK_BUILD_OK: bool | None = None
_SECRET_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{5,20}:[A-Za-z0-9_-]{20,120}\b"), "[telegram-token-redacted]"),
    (re.compile(r"\b(sk|rk|pk|xox[baprs]?)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE), "[api-token-redacted]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE), "Bearer [redacted]"),
    (
        re.compile(
            r"\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL)[A-Z0-9_]*\s*[=:]\s*)([\"']?)[^\s\"'`]+",
            re.IGNORECASE,
        ),
        r"\1\2[redacted]",
    ),
    (
        re.compile(r"\b(authorization|api[_-]?key|token|secret|password)\b\s*[:=]\s*([\"']?)[^\s\"'`]+", re.IGNORECASE),
        r"\1=\2[redacted]",
    ),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_slug(text: str, fallback: str = "task") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug or fallback)[:80]


def _task_path(task_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "", task_id)
    if safe_id != task_id or not safe_id:
        raise ValueError("Invalid task id")
    return TASK_STORE_ROOT / f"{safe_id}.json"


def _clip(value: Any, limit: int = _MAX_STORED_TEXT) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "\n...[truncated]"
    if isinstance(value, dict):
        return {key: _clip(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_clip(item, limit) for item in value]
    return value


def _redact_review_text(value: Any, limit: int = _MAX_REVIEW_OUTPUT) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    for pattern, replacement in _SECRET_REDACTIONS:
        text = pattern.sub(replacement, text)
    if len(text) > limit:
        return text[:limit].rstrip() + "\n...[truncated]"
    return text


def _redact_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a Hermes result with secrets stripped from text streams.

    run_hermes_task returns raw stdout/stderr/error that may contain tokens,
    bearer headers or API keys. This output is persisted to disk and served
    verbatim by the read-only cockpit API, so the text streams must be run
    through _SECRET_REDACTIONS before storage. A generous limit (_MAX_STORED_TEXT)
    keeps the stored output useful while still removing secrets.
    """
    if not isinstance(result, dict):
        return result
    redacted = dict(result)
    for key in ("stdout", "stderr", "error"):
        if result.get(key):
            redacted[key] = _redact_review_text(result.get(key), _MAX_STORED_TEXT)
    return redacted


def _fenced_block(content: str, language: str = "text") -> str:
    """Wrap content in a fenced code block with a collision-safe backtick fence.

    The agent output may itself contain triple-backtick code fences. A fixed
    ``` fence would be closed prematurely by those, breaking the rest of the
    markdown. Per CommonMark, an opening fence of N backticks is only closed by
    a line of at least N backticks, so we choose a fence longer than the longest
    backtick run in the content.
    """
    longest_run = 0
    for run in re.findall(r"`+", content):
        longest_run = max(longest_run, len(run))
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}{language}\n{content}\n{fence}"


def _build_review_output_summary(result: dict[str, Any]) -> list[str]:
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    error = str(result.get("error") or "")
    return [
        f"- stdout characters: `{len(stdout)}`",
        f"- stderr characters: `{len(stderr)}`",
        f"- error present: `{'yes' if error else 'no'}`",
        f"- output excerpt limit: `{_MAX_REVIEW_OUTPUT}` characters per stream",
    ]


def _sdk_root() -> Path:
    return PERSONAL_OS_ROOT / "00_System" / "SDK" / "os-sdk"


def _ensure_os_sdk_build(sdk_root: Path) -> bool:
    global _SDK_BUILD_OK
    if (sdk_root / "dist" / "index.js").exists():
        with _LOCK:
            _SDK_BUILD_OK = True
        return True
    if not (sdk_root / "package.json").exists():
        return False
    # Avoid re-running the (up to 60s) blocking npm build on every review-draft
    # if a previous attempt already failed; only retry once per process unless a
    # dist/ appears in the meantime (handled by the early return above).
    with _LOCK:
        if _SDK_BUILD_OK is False:
            return False
    npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"
    try:
        build = subprocess.run(
            [npm_cmd, "run", "build", "--silent"],
            cwd=sdk_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        with _LOCK:
            _SDK_BUILD_OK = False
        return False
    ok = build.returncode == 0 and (sdk_root / "dist" / "index.js").exists()
    with _LOCK:
        _SDK_BUILD_OK = ok
    return ok


def _write_os_draft_via_sdk(
    *,
    target_path: str,
    title: str,
    markdown_body: str,
    agent_name: str,
    reason: str,
) -> str | None:
    sdk_root = _sdk_root()
    if not _ensure_os_sdk_build(sdk_root):
        return None

    payload = {
        "targetPath": target_path,
        "title": title,
        "body": markdown_body,
        "agentName": agent_name,
        "reason": _redact_review_text(reason, 600),
    }
    node_script = r"""
import { readFile } from "node:fs/promises";
import { OS, parseMarkdownBody } from "./dist/index.js";

const input = JSON.parse(await readFile(0, "utf8"));
const now = new Date().toISOString();
const file = {
  path: input.targetPath,
  absolutePath: "",
  frontmatter: {
    id: `pos-${input.targetPath.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 96)}`,
    type: "memory",
    title: input.title,
    status: "active",
    memory_level: "session",
    created: now,
    updated: now,
    owner: "agent",
    confidence: "medium",
    source: "agent",
    tags: ["lexa", "personal-os", "agent-runtime", "hermes"],
    related: []
  },
  ast: parseMarkdownBody(input.body),
  body: input.body,
  raw: input.body
};
const result = await OS.write(file, {
  agent: input.agentName,
  reason: input.reason,
  requireApproval: true
});
console.log(JSON.stringify(result));
"""
    env = os.environ.copy()
    env["PERSONAL_OS_SDK_ROOT"] = str(PERSONAL_OS_ROOT)
    node_cmd = "node.exe" if sys.platform.startswith("win") else "node"
    try:
        proc = subprocess.run(
            [node_cmd, "--input-type=module", "-e", node_script],
            cwd=sdk_root,
            env=env,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if result.get("status") != "draft":
        return None
    draft_path = result.get("draft")
    if not isinstance(draft_path, str) or not draft_path.startswith("06_Inbox/Drafts/"):
        return None
    return draft_path


def _save_task(task: dict[str, Any]) -> dict[str, Any]:
    TASK_STORE_ROOT.mkdir(parents=True, exist_ok=True)
    task["updated_at"] = _now()
    path = _task_path(task["id"])
    with _LOCK:
        path.write_text(json.dumps(_clip(task), ensure_ascii=False, indent=2), encoding="utf-8")
    return task


def _prune_task_store(keep: int = _MAX_STORED_TASKS) -> None:
    """Keep only the newest `keep` task files to bound disk growth.

    Task filenames carry a sortable `osagt_YYYYMMDDHHMMSS_...` prefix, so we can
    order by name without a stat() per file. Best-effort: prune errors are logged
    and ignored so they never break task creation.
    """
    try:
        with _LOCK:
            # Restrict to the osagt_ prefix so foreign files cannot distort the
            # name-based ordering and cause newer tasks to be pruned.
            paths = sorted(TASK_STORE_ROOT.glob("osagt_*.json"), key=lambda p: p.name, reverse=True)
            for path in paths[keep:]:
                try:
                    path.unlink()
                except OSError:
                    logger.warning("os_agent: could not prune task file %s", path)
    except Exception:
        logger.exception("os_agent: task store pruning failed")


def _load_task(task_id: str) -> dict[str, Any]:
    path = _task_path(task_id)
    if not path.exists():
        raise KeyError(task_id)
    with _LOCK:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Task file is invalid")
    return data


def _update_task(task_id: str, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Atomically load, mutate and save a task under the shared lock.

    Runs the whole read-modify-write sequence inside _LOCK so that concurrent
    callers (e.g. _run_task and create_os_agent_review_draft) cannot overwrite
    each other's updates (lost update).
    """
    with _LOCK:
        task = _load_task(task_id)
        mutator(task)
        return _save_task(task)


def _append_evidence(task: dict[str, Any], kind: str, message: str, data: Any | None = None) -> None:
    task.setdefault("evidence", []).append({
        "time": _now(),
        "type": kind,
        "message": message,
        "data": _clip(data) if data is not None else None,
    })


def _build_worker_instructions(task: dict[str, Any]) -> str:
    return f"""Lexa OS Agent Task

Task id: {task["id"]}
Title: {task["title"]}

Role split:
- Lexa is the user-facing control plane and final decision maker.
- Personal OS is the structured context and approval layer.
- Hermes is a bounded worker for research, code, analysis and implementation support.

{LEXA_WORKER_VOICE_RULES}

Rules:
- Do not overwrite stable Personal OS memory, rules, profiles, indexes or rollups.
- If durable OS context should change, write/propose a draft only under personal_os/06_Inbox/Drafts.
- Keep facts, assumptions, ideas, decisions, evidence and tasks separate.
- Prefer one high-impact, reviewable change over broad rewrites.
- Return exact evidence, files touched, test commands and residual risks.

User task:
{task["instructions"]}
"""


def _write_review_draft(task: dict[str, Any]) -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if not result:
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _safe_slug(task.get("title", ""), "os-agent-task")
    created = _now()
    stdout = _redact_review_text(result.get("stdout"))
    stderr = _redact_review_text(result.get("stderr"))
    error = _redact_review_text(result.get("error"), 800)
    target_path = f"05_Memory/Session/{stamp}_lexa_os_agent_{slug}_{task['id']}_review.md"

    body = f"""# Lexa OS Agent Task Review

## Facts

- Task id: `{task['id']}`
- Agent: `{task.get('agent', 'hermes')}`
- Mode: `{task.get('mode', 'general')}`
- Runtime status: `{task.get('status', 'unknown')}`
- Created at: `{created}`
- Lexa workspace: local project root
- Personal OS: configured local OS root

## Assumptions

- This draft is a review surface only.
- Stable OS memory should change only after human approval.

## Decisions

- No stable OS file was intentionally overwritten by Lexa while creating this draft.
- Any durable follow-up should be reviewed before apply.

## Output Summary

{chr(10).join(_build_review_output_summary(result))}

## Evidence

{_fenced_block(stdout if stdout else '[no stdout]')}

## Errors Or Warnings

{_fenced_block(stderr or error or '[none]')}

## Tasks

- [ ] Review the agent output.
- [ ] Decide whether any durable OS memory update is needed.
- [ ] Apply only the specific approved change, not the full raw output.
"""
    return _write_os_draft_via_sdk(
        target_path=target_path,
        title=f"Lexa OS Agent Task Review - {task.get('title', 'Untitled')}",
        markdown_body=body,
        agent_name="LexaOSAgentRuntime",
        reason="Create review draft for completed OS-agent task",
    )


def get_os_agent_registry() -> dict[str, Any]:
    """Return the OS agent control-plane registry."""
    hermes = get_hermes_status()
    return {
        "status": "ok",
        "control_plane": "lexa",
        "context_layer": "personal_os",
        "task_store": str(TASK_STORE_ROOT),
        "personal_os_root": str(PERSONAL_OS_ROOT),
        "agents": [
            {
                "id": "hermes",
                "name": "Hermes",
                "role": "Bounded OS worker for background tasks",
                "available": bool(hermes.get("can_run_tasks")),
                "source_available": bool(hermes.get("source_available")),
                "safe_mode": True,
                "capabilities": [
                    "background_tasks",
                    "lexa_improvement",
                    "os_context_read",
                    "draft_only_os_updates",
                    "evidence_log",
                ],
                "status": hermes,
            },
            {
                "id": "lexa",
                "name": "Lexa",
                "role": "User-facing control plane and approval gate",
                "available": True,
                "safe_mode": True,
                "capabilities": ["routing", "approval", "review", "chat", "voice"],
            },
        ],
    }


def list_os_agent_tasks(limit: int = 30, status: str = "") -> dict[str, Any]:
    """List stored OS agent tasks, newest first."""
    limit = max(1, min(int(limit or 30), 100))
    status_filter = str(status or "").strip().lower()
    tasks: list[dict[str, Any]] = []
    TASK_STORE_ROOT.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        # Filenames carry a sortable `osagt_YYYYMMDDHHMMSS_...` prefix, so we sort
        # by name (newest first) instead of doing a stat() syscall per file.
        # Restrict to the osagt_ prefix so foreign files cannot distort ordering.
        paths = sorted(TASK_STORE_ROOT.glob("osagt_*.json"), key=lambda p: p.name, reverse=True)
        for path in paths:
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(task, dict):
                continue
            if status_filter and str(task.get("status", "")).lower() != status_filter:
                continue
            tasks.append(task)
            if len(tasks) >= limit:
                break
    return {"status": "ok", "tasks": tasks, "count": len(tasks)}


def get_os_agent_task(task_id: str) -> dict[str, Any]:
    """Return one stored OS agent task."""
    return _load_task(task_id)


def _mark_task_failed(task_id: str, exc: BaseException) -> None:
    """Best-effort: flip a task to 'failed' after an unexpected runtime error."""
    def _apply(task: dict[str, Any]) -> None:
        task["status"] = "failed"
        task["finished_at"] = _now()
        _append_evidence(
            task,
            "runtime_error",
            "Task runtime raised an unexpected error",
            {"error": _redact_review_text(f"{type(exc).__name__}: {exc}", 800)},
        )

    try:
        _update_task(task_id, _apply)
    except Exception:
        logger.exception("os_agent: failed to record failure status for task %s", task_id)


def _run_task(task_id: str) -> None:
    try:
        def _start(task: dict[str, Any]) -> None:
            task["status"] = "running"
            task["started_at"] = _now()
            _append_evidence(task, "runtime", "Task started by Lexa OS Agent Runtime")

        task = _update_task(task_id, _start)

        prompt = _build_worker_instructions(task)
        raw_result = run_hermes_task(
            prompt,
            mode=str(task.get("mode") or "lexa_improve"),
            timeout=int(task.get("timeout_seconds") or 180),
        )
        # Strip secrets from the worker output before it is persisted to disk or
        # served by the read-only cockpit API.
        result = _redact_result(raw_result)

        def _apply_result(task: dict[str, Any]) -> None:
            task["result"] = result
            task["finished_at"] = _now()
            if result.get("success"):
                task["status"] = "completed"
                _append_evidence(task, "agent_result", "Hermes completed the task", result)
            elif result.get("status") == "unavailable":
                task["status"] = "blocked"
                _append_evidence(task, "agent_blocked", "Hermes is not executable yet", result)
            else:
                task["status"] = "failed"
                _append_evidence(task, "agent_result", "Hermes returned a non-success result", result)

        task = _update_task(task_id, _apply_result)

        if task.get("create_review_draft") and task.get("status") == "completed":
            # _write_review_draft spawns subprocesses (npm/node); run it outside
            # the lock, then persist the outcome atomically.
            draft_path = _write_review_draft(task)
            if draft_path:
                def _apply_draft(task: dict[str, Any]) -> None:
                    task["review_draft_path"] = draft_path
                    _append_evidence(task, "os_draft", "Review draft created in Personal OS", {"path": draft_path})

                _update_task(task_id, _apply_draft)
    except Exception as exc:  # noqa: BLE001 - background task must never silently hang
        logger.exception("os_agent: task %s failed in runtime", task_id)
        _mark_task_failed(task_id, exc)


def start_os_agent_task(
    title: str,
    instructions: str,
    agent: str = "hermes",
    mode: str = "lexa_improve",
    timeout: int = 180,
    timeoutSeconds: int | None = None,
    createReviewDraft: bool = True,
) -> dict[str, Any]:
    """Create and start a controlled OS agent task."""
    if timeoutSeconds is not None:
        timeout = timeoutSeconds
    timeout = max(10, min(int(timeout or 180), 600))
    agent_id = (agent or "hermes").strip().lower()
    if agent_id != "hermes":
        raise ValueError(f"Unsupported OS agent: {agent}")

    task_id = f"osagt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    task = {
        "id": task_id,
        "title": (title or "OS agent task").strip()[:160],
        "instructions": (instructions or "").strip()[:8000],
        "agent": agent_id,
        "mode": mode if mode in {"general", "lexa_improve", "os_context"} else "lexa_improve",
        "status": "queued",
        "timeout_seconds": timeout,
        "create_review_draft": bool(createReviewDraft),
        "created_at": _now(),
        "updated_at": _now(),
        "paths": {
            "lexa_root": str(PROJECT_ROOT),
            "personal_os_root": str(PERSONAL_OS_ROOT),
            "workspace_root": str(HERMES_WORKSPACE_ROOT),
        },
        "evidence": [],
    }
    _append_evidence(task, "runtime", "Task queued by Lexa")
    _save_task(task)
    _prune_task_store()

    hermes = get_hermes_status()
    if not hermes.get("can_run_tasks"):
        task["status"] = "blocked"
        task["finished_at"] = _now()
        task["result"] = {
            "success": False,
            "status": "unavailable",
            "error": "Hermes source is present but no executable Hermes command is configured.",
            "status_info": hermes,
        }
        _append_evidence(task, "agent_blocked", "Hermes is not executable yet", task["result"])
        return _save_task(task)

    future = _EXECUTOR.submit(_run_task, task_id)
    future.add_done_callback(_log_task_future)
    return task


def _log_task_future(future: "Future[None]") -> None:
    """Surface exceptions from the discarded _run_task future instead of swallowing them."""
    try:
        future.result()
    except Exception:
        logger.exception("os_agent: background task future raised")


def create_os_agent_review_draft(task_id: str) -> dict[str, Any]:
    """Create a Personal OS review draft for an existing task result."""
    task = _load_task(task_id)
    draft_path = _write_review_draft(task)
    if not draft_path:
        raise ValueError("No review draft could be created for this task")

    def _apply_draft(task: dict[str, Any]) -> None:
        task["review_draft_path"] = draft_path
        _append_evidence(task, "os_draft", "Review draft created in Personal OS", {"path": draft_path})

    return _update_task(task_id, _apply_draft)
