"""Lexa AI — Routine Scheduler
Prüft minütlich welche Routinen fällig sind und führt sie aus.
Unterstützt Formate: "HH:MM" (täglich), "Mo-Fr HH:MM", "interval:Xm"
"""

import asyncio
import json
import logging
import re
from datetime import datetime

from backend import memory
from backend.security import is_command_allowed, audit_log
from backend.i18n import t

logger = logging.getLogger("lexa.scheduler")

_scheduler_task: asyncio.Task | None = None
_companion_execute = None


def _parse_schedule(schedule: str) -> bool:
    """Check if a routine should run right now."""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    current_weekday = now.weekday()  # 0=Mon, 6=Sun

    schedule = schedule.strip()

    # Format: "HH:MM" — daily
    if re.match(r"^\d{2}:\d{2}$", schedule):
        return schedule == current_time

    # Format: "Mo-Fr HH:MM" — weekday range
    day_map = {"Mo": 0, "Di": 1, "Mi": 2, "Do": 3, "Fr": 4, "Sa": 5, "So": 6}
    range_match = re.match(r"^(\w{2})-(\w{2})\s+(\d{2}:\d{2})$", schedule)
    if range_match:
        start_day = day_map.get(range_match.group(1))
        end_day = day_map.get(range_match.group(2))
        time_str = range_match.group(3)
        if start_day is not None and end_day is not None:
            if start_day <= current_weekday <= end_day and time_str == current_time:
                return True
        return False

    # Format: "Mo,Mi,Fr HH:MM" — specific days
    days_match = re.match(r"^([\w,]+)\s+(\d{2}:\d{2})$", schedule)
    if days_match:
        day_list = days_match.group(1).split(",")
        time_str = days_match.group(2)
        day_nums = [day_map.get(d.strip()) for d in day_list]
        if current_weekday in day_nums and time_str == current_time:
            return True
        return False

    # Format: "interval:Xm" or "interval:Xs" — interval-based (approximated via minute check)
    interval_match = re.match(r"^interval:(\d+)([ms])$", schedule.lower())
    if interval_match:
        value = int(interval_match.group(1))
        unit = interval_match.group(2)
        # Convert to minutes
        interval_minutes = value if unit == "m" else max(1, value // 60)
        # Fire if current minute is a multiple of interval
        current_minute_of_day = now.hour * 60 + now.minute
        return current_minute_of_day % interval_minutes == 0

    return False


async def _run_routine(routine: dict):
    """Execute all actions in a routine sequentially."""
    name = routine["name"]
    actions = routine.get("actions", [])[:20]  # Safety cap: max 20 actions per routine
    logger.info(f"Scheduler: Starte Routine '{name}' ({len(actions)} Aktionen)")
    audit_log("scheduler", "routine_start", f"ROUTINE={name}")

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        command = action.get("action") or action.get("command")
        params = action.get("params", {})

        if not command:
            continue

        permission = is_command_allowed(command)
        if permission == "blocked":
            logger.warning(t("scheduler.blocked", command=command, name=name))
            audit_log("scheduler", "blocked", f"CMD={command} ROUTINE={name}")
            continue

        if permission == "confirmation_required":
            logger.info(t("scheduler.needsConfirmation", command=command))
            audit_log("scheduler", "skipped_confirmation", f"CMD={command} ROUTINE={name}")
            continue

        try:
            if _companion_execute:
                result = _companion_execute(command, params)
                logger.info(f"Scheduler: {command} -> OK")
                audit_log("scheduler", "executed", f"CMD={command} ROUTINE={name}")
            else:
                logger.warning("Scheduler: CompanionEngine nicht verfügbar")
        except Exception as e:
            logger.error(f"Scheduler: {command} fehlgeschlagen: {e}", exc_info=True)
            audit_log("scheduler", "error", f"CMD={command} ERR={str(e)[:200]}")

    # Update last_run
    db = memory._get_db()
    try:
        db.execute(
            "UPDATE routines SET last_run = ? WHERE name = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), name),
        )
        db.commit()
    finally:
        db.close()

    audit_log("scheduler", "routine_done", f"ROUTINE={name}")
    logger.info(f"Scheduler: Routine '{name}' abgeschlossen")


async def _scheduler_loop():
    """Main scheduler loop — checks every 60 seconds.
    Also checks reminders every ~30 seconds.
    """
    logger.info("Scheduler gestartet")
    _tick = 0  # counts 30s ticks; routines run every 2nd tick (60s)
    while True:
        try:
            await asyncio.sleep(30)
            _tick += 1

            # ── Reminder check (every 30s) ──
            try:
                from backend import reminders
                fired = await asyncio.get_event_loop().run_in_executor(
                    None, reminders.reminder_check
                )
                if fired:
                    logger.info(f"Scheduler: {len(fired)} Erinnerung(en) ausgelöst")
            except Exception as e:
                logger.debug(f"Reminder check failed: {e}")

            # ── Routine check (every 60s — on even ticks) ──
            if _tick % 2 != 0:
                continue

            db = memory._get_db()
            try:
                rows = db.execute(
                    "SELECT * FROM routines WHERE enabled = 1"
                ).fetchall()
                routines = []
                for r in rows:
                    d = dict(r)
                    d["actions"] = json.loads(d["actions"])
                    routines.append(d)
            finally:
                db.close()

            for routine in routines:
                if _parse_schedule(routine["schedule"]):
                    # Check if already ran this minute
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    if routine.get("last_run") == now_str:
                        continue
                    await _run_routine(routine)

        except asyncio.CancelledError:
            logger.info("Scheduler gestoppt")
            break
        except Exception as e:
            logger.error(t("scheduler.error", error=str(e)), exc_info=True)
            await asyncio.sleep(5)  # Brief pause after error to prevent tight loops


def start_scheduler(companion_execute_fn=None):
    """Start the scheduler as an asyncio background task."""
    global _scheduler_task, _companion_execute
    _companion_execute = companion_execute_fn

    if _scheduler_task and not _scheduler_task.done():
        logger.info("Scheduler läuft bereits")
        return

    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(_scheduler_loop())
    logger.info("Routine-Scheduler gestartet (60s Intervall)")


def stop_scheduler():
    """Stop the scheduler."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
        logger.info("Scheduler gestoppt")


def get_scheduler_status() -> dict:
    """Get scheduler status."""
    running = _scheduler_task is not None and not _scheduler_task.done()
    db = memory._get_db()
    try:
        total = db.execute("SELECT COUNT(*) as c FROM routines").fetchone()["c"]
        active = db.execute("SELECT COUNT(*) as c FROM routines WHERE enabled=1").fetchone()["c"]
    finally:
        db.close()

    return {
        "running": running,
        "total_routines": total,
        "active_routines": active,
    }
