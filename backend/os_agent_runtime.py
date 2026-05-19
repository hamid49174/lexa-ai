"""Lexa OS agent runtime.

Lexa is the control plane, Personal OS is the context and approval layer,
and worker agents such as Hermes execute bounded tasks through this runtime.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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

TASK_STORE_ROOT = HERMES_WORKSPACE_ROOT / "os_agent_tasks"
_MAX_STORED_TEXT = 16000
_LOCK = threading.RLock()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lexa-os-agent")


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


def _save_task(task: dict[str, Any]) -> dict[str, Any]:
    TASK_STORE_ROOT.mkdir(parents=True, exist_ok=True)
    task["updated_at"] = _now()
    path = _task_path(task["id"])
    with _LOCK:
        path.write_text(json.dumps(_clip(task), ensure_ascii=False, indent=2), encoding="utf-8")
    return task


def _load_task(task_id: str) -> dict[str, Any]:
    path = _task_path(task_id)
    if not path.exists():
        raise KeyError(task_id)
    with _LOCK:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Task file is invalid")
    return data


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

    drafts_dir = PERSONAL_OS_ROOT / "06_Inbox" / "Drafts"
    if not drafts_dir.exists():
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _safe_slug(task.get("title", ""), "os-agent-task")
    filename = f"{stamp}_lexa_os_agent_{slug}_{task['id']}_review_draft.md"
    path = drafts_dir / filename
    created = _now()
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    error = str(result.get("error") or "").strip()

    body = f"""---
id: pos-{task['id']}
type: draft
title: Lexa OS Agent Task Review - {task.get('title', 'Untitled')}
status: review
memory_level: working
created: {created}
updated: {created}
owner: agent
confidence: medium
source: lexa-os-agent-runtime
agent: {task.get('agent', 'hermes')}
approval: pending
decision: pending
tags:
  - lexa
  - personal-os
  - agent-runtime
  - hermes
reason: Review controlled OS-agent output before applying durable context.
---
# Lexa OS Agent Task Review

## Facts

- Task id: `{task['id']}`
- Agent: `{task.get('agent', 'hermes')}`
- Mode: `{task.get('mode', 'general')}`
- Runtime status: `{task.get('status', 'unknown')}`
- Lexa root: `{PROJECT_ROOT}`
- Personal OS root: `{PERSONAL_OS_ROOT}`

## Assumptions

- This draft is a review surface only.
- Stable OS memory should change only after human approval.

## Decisions

- No stable OS file was intentionally overwritten by Lexa while creating this draft.
- Any durable follow-up should be reviewed before apply.

## Evidence

```text
{stdout[:12000] if stdout else '[no stdout]'}
```

## Errors Or Warnings

```text
{(stderr or error or '[none]')[:4000]}
```

## Tasks

- [ ] Review the agent output.
- [ ] Decide whether any durable OS memory update is needed.
- [ ] Apply only the specific approved change, not the full raw output.
"""
    with _LOCK:
        path.write_text(body, encoding="utf-8")
    return path.relative_to(PERSONAL_OS_ROOT).as_posix()


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
        paths = sorted(TASK_STORE_ROOT.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
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


def _run_task(task_id: str) -> None:
    task = _load_task(task_id)
    task["status"] = "running"
    task["started_at"] = _now()
    _append_evidence(task, "runtime", "Task started by Lexa OS Agent Runtime")
    _save_task(task)

    prompt = _build_worker_instructions(task)
    result = run_hermes_task(
        prompt,
        mode=str(task.get("mode") or "lexa_improve"),
        timeout=int(task.get("timeout_seconds") or 180),
    )
    task = _load_task(task_id)
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

    if task.get("create_review_draft") and task["status"] == "completed":
        draft_path = _write_review_draft(task)
        if draft_path:
            task["review_draft_path"] = draft_path
            _append_evidence(task, "os_draft", "Review draft created in Personal OS", {"path": draft_path})
    _save_task(task)


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

    _EXECUTOR.submit(_run_task, task_id)
    return task


def create_os_agent_review_draft(task_id: str) -> dict[str, Any]:
    """Create a Personal OS review draft for an existing task result."""
    task = _load_task(task_id)
    draft_path = _write_review_draft(task)
    if not draft_path:
        raise ValueError("No review draft could be created for this task")
    task["review_draft_path"] = draft_path
    _append_evidence(task, "os_draft", "Review draft created in Personal OS", {"path": draft_path})
    return _save_task(task)
