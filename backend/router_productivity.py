"""Lexa AI — Productivity Router (Phase 19)
API Endpoints für To-Do, Pomodoro, Habits, Time Tracking, Focus Mode
"""

import asyncio
import csv
import io
import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from backend import productivity as prod
from backend.security import check_rate_limit
from backend.i18n import t

router = APIRouter(prefix="/productivity", tags=["productivity"])


# ── VALIDATION SETS (mirror productivity.py) ──────
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
VALID_STATUSES = {"open", "in_progress", "done", "cancelled"}
VALID_CATEGORIES = {"allgemein", "arbeit", "persönlich", "einkauf", "projekt", "lernen"}
VALID_FREQUENCIES = {"daily", "weekly"}


def _validate_todo_fields(data: dict, *, require_title: bool = False) -> str | None:
    """Validate todo fields. Returns error message or None if valid."""
    if require_title and not data.get("title", "").strip():
        return "Titel darf nicht leer sein."

    status = data.get("status", "")
    if status and status not in VALID_STATUSES:
        return t("validation.invalidStatus", allowed=', '.join(sorted(VALID_STATUSES)))

    priority = data.get("priority", "")
    if priority and priority not in VALID_PRIORITIES:
        return t("validation.invalidPriority", allowed=', '.join(sorted(VALID_PRIORITIES)))

    category = data.get("category", "")
    if category and category not in VALID_CATEGORIES:
        return t("validation.invalidCategory", allowed=', '.join(sorted(VALID_CATEGORIES)))

    return None


# ── TO-DO ────────────────────────────────────────

@router.get("/todos")
async def list_todos(status: str = "", category: str = "", priority: str = ""):
    # Validate filter values if provided
    if status and status not in VALID_STATUSES:
        return JSONResponse(
            {"error": t("validation.invalidStatusFilter", allowed=', '.join(sorted(VALID_STATUSES)))},
            status_code=400,
        )
    if priority and priority not in VALID_PRIORITIES:
        return JSONResponse(
            {"error": t("validation.invalidPriorityFilter", allowed=', '.join(sorted(VALID_PRIORITIES)))},
            status_code=400,
        )
    todos = await asyncio.to_thread(prod.todo_list, status=status, category=category, priority=priority)
    return {"todos": todos}


@router.post("/todos")
async def create_todo(req: Request):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"error": t("error.invalidJson")}, status_code=400)

    error = _validate_todo_fields(data, require_title=True)
    if error:
        return JSONResponse({"error": error}, status_code=400)

    result = await asyncio.to_thread(
        prod.todo_create,
        title=data.get("title", ""),
        description=data.get("description", ""),
        priority=data.get("priority", "normal"),
        category=data.get("category", "allgemein"),
        due_date=data.get("due_date", ""),
    )
    return {"status": result}


@router.put("/todos/{todo_id}")
async def update_todo(todo_id: int, req: Request):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"error": t("error.invalidJson")}, status_code=400)

    error = _validate_todo_fields(data)
    if error:
        return JSONResponse({"error": error}, status_code=400)

    result = await asyncio.to_thread(
        prod.todo_update,
        id=todo_id,
        status=data.get("status", ""),
        title=data.get("title", ""),
        priority=data.get("priority", ""),
    )

    if isinstance(result, dict):
        return JSONResponse(result, status_code=result.get("status_code", 400))
    result_lower = str(result).lower()
    if "nicht gefunden" in result_lower or "id fehlt" in result_lower:
        return JSONResponse({"status": result}, status_code=404)

    return {"status": result}


@router.delete("/todos/completed")
async def delete_completed_todos():
    """Delete all completed (done) todos. Returns count of deleted items."""
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    # Get all done todos, then delete each
    todos = await asyncio.to_thread(prod.todo_list, status="done", category="", priority="")
    deleted = 0
    for todo in todos:
        tid = todo.get("id")
        if tid:
            await asyncio.to_thread(prod.todo_delete, id=tid)
            deleted += 1

    return {"status": f"{deleted} erledigte Todos gelöscht.", "deleted": deleted}


@router.delete("/todos/{todo_id}")
async def delete_todo(todo_id: int):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    result = await asyncio.to_thread(prod.todo_delete, id=todo_id)

    if isinstance(result, dict):
        return JSONResponse(result, status_code=result.get("status_code", 400))
    result_lower = str(result).lower()
    if "nicht gefunden" in result_lower or "id fehlt" in result_lower:
        return JSONResponse({"status": result}, status_code=404)

    return {"status": result}


@router.post("/todos/{todo_id}/complete")
async def complete_todo(todo_id: int):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    result = await asyncio.to_thread(prod.todo_complete, id=todo_id)

    if isinstance(result, dict):
        return JSONResponse(result, status_code=result.get("status_code", 400))
    if "nicht gefunden" in str(result).lower():
        return JSONResponse({"status": result}, status_code=404)

    return {"status": result}


# ── POMODORO ─────────────────────────────────────

@router.get("/pomodoro")
async def pomodoro_status():
    return await asyncio.to_thread(prod.pomodoro_status)


@router.post("/pomodoro/start")
async def pomodoro_start(req: Request):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"error": t("error.invalidJson")}, status_code=400)
    try:
        duration = int(data.get("duration", 25))
    except (ValueError, TypeError):
        return JSONResponse({"error": "duration muss eine Zahl sein (1-120)."}, status_code=400)
    duration = max(1, min(120, duration))
    result = await asyncio.to_thread(
        prod.pomodoro_start,
        task=str(data.get("task", ""))[:200],
        duration=duration,
    )
    return {"status": result}


@router.post("/pomodoro/stop")
async def pomodoro_stop():
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    result = await asyncio.to_thread(prod.pomodoro_stop)
    return {"status": result}


@router.post("/pomodoro/acknowledge")
async def pomodoro_acknowledge():
    result = await asyncio.to_thread(prod.pomodoro_acknowledge)
    return {"status": result}


# ── HABITS ───────────────────────────────────────

@router.get("/habits")
async def list_habits():
    habits = await asyncio.to_thread(prod.habit_list)
    return {"habits": habits}


@router.post("/habits")
async def create_habit(req: Request):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"error": t("error.invalidJson")}, status_code=400)

    name = data.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Name darf nicht leer sein."}, status_code=400)

    frequency = data.get("frequency", "daily")
    if frequency not in VALID_FREQUENCIES:
        return JSONResponse(
            {"error": t("validation.invalidFrequency", allowed=', '.join(sorted(VALID_FREQUENCIES)))},
            status_code=400,
        )

    target = data.get("target", 1)
    try:
        target = int(target)
        target = max(1, min(100, target))
    except (ValueError, TypeError):
        return JSONResponse({"error": "Target muss eine Zahl sein (1-100)."}, status_code=400)

    result = await asyncio.to_thread(
        prod.habit_create,
        name=name,
        description=data.get("description", ""),
        frequency=frequency,
        target=target,
    )
    return {"status": result}


@router.post("/habits/{name}/log")
async def log_habit(name: str, req: Request):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    try:
        data = await req.json()
    except Exception:
        data = {}
    try:
        count = int(data.get("count", 1)) if data else 1
    except (ValueError, TypeError):
        return JSONResponse({"error": "count muss eine Zahl sein."}, status_code=400)
    count = max(1, min(100, count))
    result = await asyncio.to_thread(prod.habit_log, name=name, count=count)

    if isinstance(result, dict):
        return JSONResponse(result, status_code=result.get("status_code", 400))
    if "nicht gefunden" in str(result).lower():
        return JSONResponse({"status": result}, status_code=404)

    return {"status": result}


@router.delete("/habits/{name}")
async def delete_habit(name: str):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    result = await asyncio.to_thread(prod.habit_delete, name=name)

    if isinstance(result, dict):
        return JSONResponse(result, status_code=result.get("status_code", 400))
    if "nicht gefunden" in str(result).lower():
        return JSONResponse({"status": result}, status_code=404)

    return {"status": result}


@router.get("/habits/stats")
async def habits_stats():
    return await asyncio.to_thread(prod.habit_stats)


# ── TIME TRACKING ────────────────────────────────

@router.get("/time-tracking")
async def time_tracking_status():
    return await asyncio.to_thread(prod.time_tracking_status)


@router.post("/time-tracking/start")
async def time_tracking_start():
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    result = await asyncio.to_thread(prod.time_tracking_start)
    return {"status": result}


@router.post("/time-tracking/stop")
async def time_tracking_stop():
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    result = await asyncio.to_thread(prod.time_tracking_stop)
    return {"status": result}


@router.get("/time-tracking/report")
async def time_tracking_report(days: int = 1):
    days = max(1, min(365, days))
    report = await asyncio.to_thread(prod.time_tracking_report, days=days)
    return {"report": report, "days": days}


# ── FOCUS MODE ───────────────────────────────────

@router.get("/focus")
async def focus_status():
    return await asyncio.to_thread(prod.focus_mode_status)


@router.post("/focus/on")
async def focus_on(req: Request):
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)
    try:
        data = await req.json()
    except Exception:
        data = {}
    sites = data.get("sites", "")
    result = await asyncio.to_thread(prod.focus_mode_on, sites=sites)
    return {"status": result}


@router.post("/focus/off")
async def focus_off():
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit überschritten."}, status_code=429)

    result = await asyncio.to_thread(prod.focus_mode_off)
    return {"status": result}


# ── STATS ────────────────────────────────────────

@router.get("/stats")
async def productivity_stats():
    return await asyncio.to_thread(prod.productivity_stats)


@router.get("/weekly")
async def weekly_stats(days: int = 7):
    days = max(1, min(days, 30))
    return {"days": await asyncio.to_thread(prod.weekly_stats, days)}


# ── EXPORT ───────────────────────────────────────

@router.get("/export")
async def export_productivity(format: str = "json"):
    """Export all productivity data as JSON or CSV."""
    if format not in ("json", "csv"):
        return JSONResponse(
            {"error": t("validation.invalidFormat")},
            status_code=400,
        )

    # Collect all data in parallel
    todos_task = asyncio.to_thread(prod.todo_list, status="", category="", priority="")
    habits_task = asyncio.to_thread(prod.habit_list)
    stats_task = asyncio.to_thread(prod.productivity_stats)

    todos, habits, stats = await asyncio.gather(todos_task, habits_task, stats_task)

    if format == "json":
        export_data = {
            "todos": todos,
            "habits": habits,
            "stats": stats,
        }
        content = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=lexa_productivity.json"},
        )

    # CSV format: export todos as CSV (most tabular data)
    output = io.StringIO()
    writer = csv.writer(output)

    # Todos section
    writer.writerow(["# Todos"])
    if todos:
        headers = list(todos[0].keys())
        writer.writerow(headers)
        for todo in todos:
            writer.writerow([todo.get(h, "") for h in headers])
    else:
        writer.writerow([t("productivity.noTodos")])

    writer.writerow([])
    writer.writerow(["# Habits"])
    if habits:
        headers = [k for k in habits[0].keys() if k != "week"]
        writer.writerow(headers)
        for habit in habits:
            writer.writerow([habit.get(h, "") for h in headers])
    else:
        writer.writerow([t("productivity.noHabits")])

    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lexa_productivity.csv"},
    )
