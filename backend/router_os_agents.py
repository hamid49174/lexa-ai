"""Lexa OS agent runtime API."""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.os_agent_runtime import (
    create_os_agent_review_draft,
    get_os_agent_registry,
    get_os_agent_task,
    list_os_agent_tasks,
    start_os_agent_task,
)
from backend.security import audit_log, check_rate_limit, sanitize_input

logger = logging.getLogger("lexa.os_agents")

router = APIRouter(prefix="/os", tags=["os-agents"])


class OSAgentTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    # sanitize_input (security.py) kappt hart auf 2000 Zeichen; das Limit hier
    # muss konsistent sein, sonst werden 2000-8000 Zeichen still abgeschnitten.
    instructions: str = Field(..., min_length=1, max_length=2000)
    agent: Literal["hermes"] = "hermes"
    mode: Literal["general", "lexa_improve", "os_context"] = "lexa_improve"
    timeoutSeconds: int = Field(180, ge=10, le=600)
    createReviewDraft: bool = True


@router.get("/agents")
async def os_agents():
    """Return the Lexa OS agent registry."""
    if not check_rate_limit("audit_read"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return await asyncio.to_thread(get_os_agent_registry)


@router.get("/tasks")
async def os_tasks(
    limit: int = Query(30, ge=1, le=100),
    status: str = Query("", max_length=40),
):
    """List Lexa OS agent tasks."""
    if not check_rate_limit("audit_read"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return await asyncio.to_thread(list_os_agent_tasks, limit, status)


@router.get("/tasks/{task_id}")
async def os_task(task_id: str):
    """Return one Lexa OS agent task."""
    if not check_rate_limit("audit_read"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    try:
        return await asyncio.to_thread(get_os_agent_task, task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="OS agent task not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/tasks")
async def os_task_start(req: OSAgentTaskRequest):
    """Start a controlled Lexa OS agent task."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    title = sanitize_input(req.title)
    instructions = sanitize_input(req.instructions)
    audit_log("os_agent", "task_start", f"agent={req.agent} mode={req.mode} title={title[:80]}")
    try:
        return await asyncio.to_thread(
            start_os_agent_task,
            title,
            instructions,
            req.agent,
            req.mode,
            req.timeoutSeconds,
            None,
            req.createReviewDraft,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("OS agent task start failed")
        raise HTTPException(status_code=502, detail=f"OS agent task failed: {exc}")


@router.post("/tasks/{task_id}/review-draft")
async def os_task_review_draft(task_id: str):
    """Create a Personal OS review draft for a completed OS agent task."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    audit_log("os_agent", "review_draft", f"task={task_id}")
    try:
        return await asyncio.to_thread(create_os_agent_review_draft, task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="OS agent task not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
