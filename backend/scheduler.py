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
from backend.agent_reflection import reflect_action
from backend.security import (
    audit_error_details,
    audit_log,
    audit_safe_token,
    audit_value_metadata,
    is_command_allowed,
    validate_params,
)
from backend.tool_registry import ToolSchemaValidationError, validate_tool_arguments
from backend.i18n import t

logger = logging.getLogger("lexa.scheduler")

_scheduler_task: asyncio.Task | None = None
_companion_execute = None


def _routine_audit_details(
    routine_name: object,
    *,
    command: object | None = None,
    error: object | None = None,
    reason: object | None = None,
) -> str:
    parts = [audit_value_metadata("routine", routine_name)]
    if command is not None:
        parts.append(f"cmd={audit_safe_token(command)}")
    if error is not None:
        parts.append(audit_error_details(error, source="scheduler"))
    if reason is not None:
        parts.append(audit_value_metadata("reason", reason))
    return " ".join(parts)


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
        day_list = [d.strip() for d in days_match.group(1).split(",")]
        time_str = days_match.group(2)
        # Ungültige Tageskürzel sichtbar machen, damit Tippfehler nicht
        # stillschweigend dazu führen, dass die Routine nie läuft.
        invalid = [d for d in day_list if day_map.get(d) is None]
        if invalid:
            logger.warning(
                "Scheduler: unbekannte Tageskürzel %s im Schedule '%s' — werden ignoriert",
                invalid,
                schedule,
            )
        day_nums = [day_map[d] for d in day_list if day_map.get(d) is not None]
        if current_weekday in day_nums and time_str == current_time:
            return True
        return False

    # Format: "interval:Xm" or "interval:Xs" — interval-based.
    # WICHTIG: Der Scheduler tickt effektiv nur minütlich (Routinen laufen alle
    # 60s) und dedupliziert last_run minutengenau. Daher wird ausschließlich
    # Minuten-Granularität unterstützt. Sekunden-Intervalle < 60s oder solche,
    # die kein ganzzahliges Vielfaches einer Minute sind, werden abgelehnt,
    # damit keine still wirkungslose Konfiguration entsteht.
    interval_match = re.match(r"^interval:(\d+)([ms])$", schedule.lower())
    if interval_match:
        value = int(interval_match.group(1))
        unit = interval_match.group(2)
        if unit == "m":
            interval_minutes = value
        else:  # unit == "s"
            if value < 60 or value % 60 != 0:
                logger.warning(
                    "Scheduler: Sekunden-Intervall '%s' nicht unterstützt — "
                    "nur Minuten-Granularität (>= 60s, Vielfaches von 60s) möglich",
                    schedule,
                )
                return False
            interval_minutes = value // 60
        if interval_minutes < 1:
            logger.warning("Scheduler: ungültiges Intervall '%s' (< 1 Minute)", schedule)
            return False
        # Fire if current minute is a multiple of interval
        current_minute_of_day = now.hour * 60 + now.minute
        return current_minute_of_day % interval_minutes == 0

    return False


async def _run_routine(routine: dict):
    """Execute all actions in a routine sequentially."""
    name = routine["name"]
    actions = routine.get("actions", [])[:20]  # Safety cap: max 20 actions per routine
    logger.info(f"Scheduler: Starte Routine '{name}' ({len(actions)} Aktionen)")
    audit_log("scheduler", "routine_start", _routine_audit_details(name))

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        command = action.get("action") or action.get("command")
        params = action.get("params", {})

        if not command:
            continue

        try:
            schema_params = validate_tool_arguments(command, params)
        except ToolSchemaValidationError as e:
            logger.warning("Scheduler: invalid tool args for %s in routine %s: %s", command, name, e)
            audit_log("scheduler", "tool_schema_invalid", _routine_audit_details(name, command=command, error=e))
            continue

        permission = is_command_allowed(command)
        reflection = reflect_action(
            command,
            schema_params,
            permission=permission,
            source="scheduler",
            plan_length=len(actions),
        )
        if reflection is not None and not reflection.should_execute:
            logger.warning("Scheduler: reflection blocked %s in routine %s: %s", command, name, reflection.reason)
            audit_log(
                "scheduler",
                "reflection_blocked",
                _routine_audit_details(name, command=command, reason=reflection.reason),
            )
            continue

        if permission == "blocked":
            logger.warning(t("scheduler.blocked", command=command, name=name))
            audit_log("scheduler", "blocked", _routine_audit_details(name, command=command))
            continue

        if permission in {"confirmation_required", "unknown"}:
            logger.info(t("scheduler.needsConfirmation", command=command))
            audit_log("scheduler", "skipped_confirmation", _routine_audit_details(name, command=command))
            continue

        try:
            safe_params = validate_params(command, schema_params)
        except ValueError as e:
            logger.warning("Scheduler: blocked params for %s in routine %s: %s", command, name, e)
            audit_log("scheduler", "param_blocked", _routine_audit_details(name, command=command, error=e))
            continue

        try:
            if _companion_execute:
                _companion_execute(command, safe_params)
                logger.info(f"Scheduler: {command} -> OK")
                audit_log("scheduler", "executed", _routine_audit_details(name, command=command))
            else:
                logger.warning("Scheduler: CompanionEngine nicht verfügbar")
        except Exception as e:
            logger.error(f"Scheduler: {command} fehlgeschlagen: {e}", exc_info=True)
            audit_log("scheduler", "error", _routine_audit_details(name, command=command, error=e))

    # Update last_run
    # Die thread-lokale Verbindung NICHT schließen — sie persistiert bewusst
    # im thread_local (siehe memory._get_db).
    db = memory._get_db()
    db.execute(
        "UPDATE routines SET last_run = ? WHERE name = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), name),
    )
    db.commit()

    audit_log("scheduler", "routine_done", _routine_audit_details(name))
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

            # Thread-lokale Verbindung nicht schließen (persistiert im thread_local).
            db = memory._get_db()
            rows = db.execute(
                "SELECT * FROM routines WHERE enabled = 1"
            ).fetchall()
            routines = []
            for r in rows:
                d = dict(r)
                d["actions"] = json.loads(d["actions"])
                routines.append(d)

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
    # Thread-lokale Verbindung nicht schließen (persistiert im thread_local).
    db = memory._get_db()
    total = db.execute("SELECT COUNT(*) as c FROM routines").fetchone()["c"]
    active = db.execute("SELECT COUNT(*) as c FROM routines WHERE enabled=1").fetchone()["c"]

    return {
        "running": running,
        "total_routines": total,
        "active_routines": active,
    }
