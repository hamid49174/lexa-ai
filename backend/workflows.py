"""Lexa Workflow Engine — Automatisierte Ablaeufe mit Zeitplan und Event-Triggern.
Workflows werden als JSON in SQLite gespeichert (lexa_memory.db).
Unterstuetzt Cron-Schedules, Event-basierte Trigger und manuelle Ausfuehrung.
Thread-safe, async-kompatibel, integriert mit bestehender CompanionEngine.
"""

import asyncio
import base64
import ipaddress
import json
import logging
import re
import sqlite3
import socket
import subprocess
import threading
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from backend.config import LEXA_DATA_DIR
from backend.security import is_dangerous_network_ip

logger = logging.getLogger("lexa.workflows")

DB_PATH = LEXA_DATA_DIR / "lexa_memory.db"
MAX_TEMPLATE_DEPTH = 5
WORKFLOW_BACKOFF_AFTER_FAILURES = 3
WORKFLOW_BACKOFF_AFTER_MORE_FAILURES = 5
WORKFLOW_AUTO_DISABLE_AFTER_FAILURES = 10
_thread_local = threading.local()

# ══════════════════════════════════════════════════


def _validate_workflow_http_url(url: str) -> str:
    from backend.security import validate_url

    normalized_url = validate_url(url)
    parsed = urlparse(normalized_url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("HTTP-URL ohne Host nicht erlaubt.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        resolved = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return normalized_url

    for _, _, _, _, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if is_dangerous_network_ip(ip):
            raise ValueError(f"Zugriff auf private IP-Adressen nicht erlaubt: {hostname}")
    return normalized_url


class _SafeWorkflowRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        safe_target = _validate_workflow_http_url(target)
        return super().redirect_request(req, fp, code, msg, headers, safe_target)


#  DATA MODEL
# ══════════════════════════════════════════════════

@dataclass
class Workflow:
    """Repraesentiert einen automatisierten Workflow."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    enabled: bool = True
    trigger: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    last_run: Optional[str] = None
    run_count: int = 0
    last_result: Optional[str] = None  # "success" | "error" | None
    failure_count: int = 0
    next_retry_at: Optional[str] = None
    disabled_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "trigger": self.trigger,
            "steps": self.steps,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "last_result": self.last_result,
            "failure_count": self.failure_count,
            "next_retry_at": self.next_retry_at,
            "disabled_reason": self.disabled_reason,
        }


# ══════════════════════════════════════════════════
#  CRON PARSER — Einfacher 5-Feld Cron Matcher
#  Format: minute hour day_of_month month day_of_week
#  Unterstuetzt: *, Zahlen, Bereiche (1-5), Listen (1,3,5), Schritte (*/5)
# ══════════════════════════════════════════════════

def _cron_field_matches(field_expr: str, current_value: int, max_value: int) -> bool:
    """Prueft ob ein Cron-Feld auf den aktuellen Wert passt."""
    if field_expr == "*":
        return True

    for part in field_expr.split(","):
        part = part.strip()

        # Step: */5 or 1-10/2
        if "/" in part:
            range_part, step_str = part.split("/", 1)
            try:
                step = int(step_str)
            except ValueError:
                continue
            if step <= 0:
                continue

            if range_part == "*":
                if current_value % step == 0:
                    return True
            elif "-" in range_part:
                try:
                    start, end = range_part.split("-", 1)
                    start, end = int(start), int(end)
                    if start <= current_value <= end and (current_value - start) % step == 0:
                        return True
                except ValueError:
                    continue
            continue

        # Range: 1-5
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                start, end = int(start), int(end)
                if start <= current_value <= end:
                    return True
            except ValueError:
                continue
            continue

        # Single value
        try:
            if int(part) == current_value:
                return True
        except ValueError:
            continue

    return False


def _cron_matches(cron_expr: str, dt: Optional[datetime] = None) -> bool:
    """Prueft ob ein 5-Feld Cron-Ausdruck auf den aktuellen Zeitpunkt passt.
    Format: minute hour day_of_month month day_of_week
    day_of_week: 0=Sonntag, 1=Montag, ..., 6=Samstag (oder 7=Sonntag)
    """
    if not cron_expr or not cron_expr.strip():
        return False

    dt = dt or datetime.now()
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        logger.warning(f"Ungueltiger Cron-Ausdruck: '{cron_expr}' (erwartet 5 Felder)")
        return False

    minute_expr, hour_expr, dom_expr, month_expr, dow_expr = parts

    # Python weekday: 0=Monday. Cron: 0=Sunday.
    # Convert Python weekday to cron: (py_weekday + 1) % 7
    cron_dow = (dt.weekday() + 1) % 7

    if not _cron_field_matches(minute_expr, dt.minute, 59):
        return False
    if not _cron_field_matches(hour_expr, dt.hour, 23):
        return False
    if not _cron_field_matches(dom_expr, dt.day, 31):
        return False
    if not _cron_field_matches(month_expr, dt.month, 12):
        return False
    if not _cron_field_matches(dow_expr, cron_dow, 7):
        return False

    return True


def _daily_at_matches(time_str: str, dt: Optional[datetime] = None) -> bool:
    """Prueft ob 'HH:MM' auf aktuelle Zeit passt."""
    dt = dt or datetime.now()
    return dt.strftime("%H:%M") == time_str.strip()


def _interval_matches(interval_minutes: int, dt: Optional[datetime] = None) -> bool:
    """Prueft ob das aktuelle Minuten-Offset ein Vielfaches des Intervalls ist."""
    if interval_minutes <= 0:
        return False
    dt = dt or datetime.now()
    total_minutes = dt.hour * 60 + dt.minute
    return total_minutes % interval_minutes == 0


# ══════════════════════════════════════════════════
#  WORKFLOW ENGINE (Singleton)
# ══════════════════════════════════════════════════

class WorkflowEngine:
    """Zentrale Workflow-Engine — verwaltet Workflows, fuehrt sie aus,
    reagiert auf Events und prueft Cron-Schedules."""

    _instance: Optional["WorkflowEngine"] = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._db_lock = threading.Lock()
        self._event_handlers: dict[str, list] = {}  # event_name -> [workflow_ids]
        self._scheduler_task: Optional[asyncio.Task] = None
        self._companion_execute = None
        self._tables_ready = False
        self._db_path: str | None = None
        self._initialized = True
        logger.info("WorkflowEngine initialisiert")

    # ── Database ──────────────────────────────────

    def _get_db(self) -> sqlite3.Connection:
        """Thread-lokale DB-Verbindung mit WAL-Modus."""
        db_path = str(DB_PATH)
        db = getattr(_thread_local, "workflow_db", None)
        cached_path = getattr(_thread_local, "workflow_db_path", None)
        if db is None or cached_path != db_path:
            self._close_thread_db()
            db = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            _thread_local.workflow_db = db
            _thread_local.workflow_db_path = db_path

        if self._db_path != db_path:
            with self._db_lock:
                if self._db_path != db_path:
                    self._tables_ready = False
                    self._db_path = db_path
        self._ensure_tables(db)
        return db

    def _release_db(self, db: sqlite3.Connection) -> None:
        """No-op fuer call sites, die frueher pro Zugriff geschlossen haben."""
        return None

    def _close_thread_db(self) -> None:
        """Schliesst die thread-lokale Workflow-DB-Verbindung."""
        db = getattr(_thread_local, "workflow_db", None)
        if db is not None:
            try:
                db.close()
            except sqlite3.Error:
                pass
        _thread_local.workflow_db = None
        _thread_local.workflow_db_path = None

    def _ensure_tables(self, db: sqlite3.Connection) -> None:
        """Erstellt die Workflow-Tabellen falls nicht vorhanden."""
        if self._tables_ready:
            return
        with self._db_lock:
            if self._tables_ready:
                return
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    trigger_config TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
                    last_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    last_result TEXT,
                    failure_count INTEGER DEFAULT 0,
                    next_retry_at TEXT,
                    disabled_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS workflow_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT,
                    result TEXT,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_workflows_enabled ON workflows(enabled);
                CREATE INDEX IF NOT EXISTS idx_workflow_logs_wf_id ON workflow_logs(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_logs_started ON workflow_logs(started_at);
            """)
            for column, definition in (
                ("failure_count", "INTEGER DEFAULT 0"),
                ("next_retry_at", "TEXT"),
                ("disabled_reason", "TEXT"),
            ):
                try:
                    db.execute(f"SELECT {column} FROM workflows LIMIT 1")
                except sqlite3.OperationalError:
                    db.execute(f"ALTER TABLE workflows ADD COLUMN {column} {definition}")
            db.execute("CREATE INDEX IF NOT EXISTS idx_workflows_retry ON workflows(enabled, next_retry_at)")
            db.commit()
            self._tables_ready = True
            logger.info("Workflow-Tabellen erstellt/verifiziert")

    def _workflow_backoff_minutes(self, failure_count: int) -> Optional[int]:
        if failure_count >= WORKFLOW_AUTO_DISABLE_AFTER_FAILURES:
            return None
        if failure_count >= WORKFLOW_BACKOFF_AFTER_MORE_FAILURES:
            return 30
        if failure_count >= WORKFLOW_BACKOFF_AFTER_FAILURES:
            return 5
        return 0

    def _parse_workflow_time(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        for candidate in (text, text.replace(" ", "T", 1)):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    def _workflow_in_backoff(self, wf: dict, now: Optional[datetime] = None) -> bool:
        next_retry = self._parse_workflow_time(wf.get("next_retry_at"))
        return bool(next_retry and next_retry > (now or datetime.now()))

    def _workflow_backoff_state(self, current_failures: Any, finished_at: datetime) -> dict:
        try:
            failure_count = max(0, int(current_failures or 0)) + 1
        except (TypeError, ValueError):
            failure_count = 1

        minutes = self._workflow_backoff_minutes(failure_count)
        if minutes is None:
            return {
                "failure_count": failure_count,
                "next_retry_at": None,
                "enabled": 0,
                "disabled_reason": f"Automatisch deaktiviert nach {failure_count} Fehlern in Folge.",
            }
        if minutes > 0:
            return {
                "failure_count": failure_count,
                "next_retry_at": (finished_at + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"),
                "enabled": 1,
                "disabled_reason": None,
            }
        return {
            "failure_count": failure_count,
            "next_retry_at": None,
            "enabled": 1,
            "disabled_reason": None,
        }

    # ── CRUD ──────────────────────────────────────

    def create_workflow(self, data: dict) -> dict:
        """Erstellt einen neuen Workflow und speichert ihn in SQLite."""
        if not data.get("name"):
            return {"error": "Name ist erforderlich."}

        workflow = Workflow(
            name=data["name"][:200],
            description=data.get("description", "")[:1000],
            enabled=data.get("enabled", True),
            trigger=data.get("trigger", {"type": "manual"}),
            steps=data.get("steps", []),
        )

        # Validierung
        trigger_type = workflow.trigger.get("type")
        if trigger_type not in ("schedule", "event", "manual"):
            return {"error": f"Ungueltiger Trigger-Typ: '{trigger_type}'. Erlaubt: schedule, event, manual"}

        if not workflow.steps:
            return {"error": "Mindestens ein Step ist erforderlich."}

        if len(workflow.steps) > 50:
            return {"error": "Maximal 50 Steps pro Workflow erlaubt."}

        db = self._get_db()
        try:
            db.execute(
                """INSERT INTO workflows (id, name, description, enabled, trigger_config, steps, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    workflow.id,
                    workflow.name,
                    workflow.description,
                    1 if workflow.enabled else 0,
                    json.dumps(workflow.trigger, ensure_ascii=False),
                    json.dumps(workflow.steps, ensure_ascii=False),
                    workflow.created_at,
                    workflow.updated_at,
                ),
            )
            db.commit()
            logger.info(f"Workflow erstellt: '{workflow.name}' (ID: {workflow.id})")

            # Event-Handler registrieren falls Event-Trigger
            if trigger_type == "event":
                event_name = workflow.trigger.get("event", "")
                if event_name:
                    self._event_handlers.setdefault(event_name, []).append(workflow.id)

            return workflow.to_dict()
        except sqlite3.IntegrityError as e:
            return {"error": f"Workflow konnte nicht erstellt werden: {e}"}
        finally:
            self._release_db(db)

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        """Laedt einen einzelnen Workflow."""
        db = self._get_db()
        try:
            row = db.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)
        finally:
            self._release_db(db)

    def list_workflows(self) -> list[dict]:
        """Listet alle Workflows auf."""
        db = self._get_db()
        try:
            rows = db.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            self._release_db(db)

    def update_workflow(self, workflow_id: str, data: dict) -> dict:
        """Aktualisiert einen bestehenden Workflow."""
        db = self._get_db()
        try:
            existing = db.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
            if not existing:
                return {"error": f"Workflow '{workflow_id}' nicht gefunden."}

            updates: list[str] = []
            params: list = []

            if "name" in data:
                updates.append("name = ?")
                params.append(data["name"][:200])
            if "description" in data:
                updates.append("description = ?")
                params.append(data["description"][:1000])
            if "enabled" in data:
                updates.append("enabled = ?")
                params.append(1 if data["enabled"] else 0)
                if data["enabled"]:
                    updates.extend(["failure_count = ?", "next_retry_at = ?", "disabled_reason = ?"])
                    params.extend([0, None, None])
            if "trigger" in data:
                trigger_type = data["trigger"].get("type")
                if trigger_type not in ("schedule", "event", "manual"):
                    return {"error": f"Ungueltiger Trigger-Typ: '{trigger_type}'"}
                updates.append("trigger_config = ?")
                params.append(json.dumps(data["trigger"], ensure_ascii=False))
            if "steps" in data:
                if len(data["steps"]) > 50:
                    return {"error": "Maximal 50 Steps pro Workflow erlaubt."}
                updates.append("steps = ?")
                params.append(json.dumps(data["steps"], ensure_ascii=False))

            if not updates:
                return {"error": "Keine Aenderungen angegeben."}

            updates.append("updated_at = ?")
            params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            params.append(workflow_id)

            db.execute(
                f"UPDATE workflows SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            db.commit()
            logger.info(f"Workflow aktualisiert: {workflow_id}")
            return self.get_workflow(workflow_id) or {"error": "Workflow nicht gefunden nach Update."}
        finally:
            self._release_db(db)

    def delete_workflow(self, workflow_id: str) -> dict:
        """Loescht einen Workflow und seine Logs."""
        db = self._get_db()
        try:
            result = db.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            if result.rowcount == 0:
                return {"error": f"Workflow '{workflow_id}' nicht gefunden."}
            db.execute("DELETE FROM workflow_logs WHERE workflow_id = ?", (workflow_id,))
            db.commit()

            # Event-Handler entfernen
            for event_name, wf_ids in self._event_handlers.items():
                if workflow_id in wf_ids:
                    wf_ids.remove(workflow_id)

            logger.info(f"Workflow geloescht: {workflow_id}")
            return {"success": True, "deleted_id": workflow_id}
        finally:
            self._release_db(db)

    def enable_workflow(self, workflow_id: str) -> dict:
        """Aktiviert einen Workflow."""
        return self.update_workflow(workflow_id, {"enabled": True})

    def disable_workflow(self, workflow_id: str) -> dict:
        """Deaktiviert einen Workflow."""
        return self.update_workflow(workflow_id, {"enabled": False})

    def get_workflow_logs(self, workflow_id: str, limit: int = 50) -> list[dict]:
        """Gibt die letzten Ausfuehrungs-Logs eines Workflows zurueck."""
        limit = max(1, min(limit, 200))
        db = self._get_db()
        try:
            rows = db.execute(
                "SELECT * FROM workflow_logs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT ?",
                (workflow_id, limit),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                # Parse JSON result field
                if d.get("result"):
                    try:
                        d["result"] = json.loads(d["result"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                result.append(d)
            return result
        finally:
            self._release_db(db)

    # ── Execution ─────────────────────────────────

    async def run_workflow(self, workflow_id: str) -> dict:
        """Fuehrt einen Workflow asynchron aus."""
        wf_data = self.get_workflow(workflow_id)
        if not wf_data:
            return {"error": f"Workflow '{workflow_id}' nicht gefunden."}

        logger.info(f"Workflow gestartet: '{wf_data['name']}' (ID: {workflow_id})")
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        step_results: list[dict] = []
        workflow_steps = wf_data.get("steps", [])
        context: dict[str, Any] = {
            "prev_result": None,
            "workflow_id": workflow_id,
            "workflow_step_count": len(workflow_steps),
        }
        overall_status = "success"
        error_msg = None

        try:
            for i, step in enumerate(workflow_steps):
                step_num = i + 1
                logger.info(f"  Step {step_num}/{len(wf_data['steps'])}: {step.get('type', 'unknown')}")

                try:
                    result = await self._execute_step(step, context)
                    step_results.append({
                        "step": step_num,
                        "type": step.get("type"),
                        "status": "success",
                        "result": result,
                    })
                    context["prev_result"] = result
                except Exception as e:
                    logger.error(f"  Step {step_num} fehlgeschlagen: {e}", exc_info=True)
                    step_results.append({
                        "step": step_num,
                        "type": step.get("type"),
                        "status": "error",
                        "error": str(e),
                    })
                    overall_status = "error"
                    error_msg = f"Step {step_num} ({step.get('type')}): {e}"
                    # Continue with next step instead of aborting
                    context["prev_result"] = {"error": str(e)}

        except Exception as e:
            overall_status = "error"
            error_msg = str(e)
            logger.error(f"Workflow-Ausfuehrung fehlgeschlagen: {e}", exc_info=True)

        finished_dt = datetime.now()
        finished_at = finished_dt.strftime("%Y-%m-%d %H:%M:%S")
        current_enabled = 1 if wf_data.get("enabled", True) else 0
        if overall_status == "success":
            backoff_state = {
                "failure_count": 0,
                "next_retry_at": None,
                "enabled": current_enabled,
                "disabled_reason": None,
            }
        else:
            backoff_state = self._workflow_backoff_state(wf_data.get("failure_count"), finished_dt)
            if not current_enabled:
                backoff_state["enabled"] = 0

        # Log speichern und Workflow aktualisieren
        db = self._get_db()
        try:
            db.execute(
                """INSERT INTO workflow_logs (workflow_id, started_at, finished_at, status, result, error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    workflow_id,
                    started_at,
                    finished_at,
                    overall_status,
                    json.dumps(step_results, ensure_ascii=False, default=str),
                    error_msg,
                ),
            )
            db.execute(
                """UPDATE workflows
                      SET last_run = ?,
                          run_count = run_count + 1,
                          last_result = ?,
                          failure_count = ?,
                          next_retry_at = ?,
                          enabled = ?,
                          disabled_reason = ?
                   WHERE id = ?""",
                (
                    finished_at,
                    overall_status,
                    backoff_state["failure_count"],
                    backoff_state["next_retry_at"],
                    backoff_state["enabled"],
                    backoff_state["disabled_reason"],
                    workflow_id,
                ),
            )
            db.commit()
        finally:
            self._release_db(db)

        logger.info(f"Workflow beendet: '{wf_data['name']}' — Status: {overall_status}")
        return {
            "workflow_id": workflow_id,
            "name": wf_data["name"],
            "status": overall_status,
            "started_at": started_at,
            "finished_at": finished_at,
            "steps": step_results,
            "error": error_msg,
        }

    async def _execute_step(self, step: dict, context: dict) -> Any:
        """Fuehrt einen einzelnen Step aus. Unterstuetzt verschiedene Step-Typen."""
        step_type = step.get("type", "")

        if step_type == "tool":
            return await self._step_tool(step, context)
        elif step_type == "ai_prompt":
            return await self._step_ai_prompt(step, context)
        elif step_type == "condition":
            return await self._step_condition(step, context)
        elif step_type == "delay":
            return await self._step_delay(step)
        elif step_type == "notify":
            return await self._step_notify(step, context)
        elif step_type == "http":
            return await self._step_http(step, context)
        else:
            raise ValueError(f"Unbekannter Step-Typ: '{step_type}'")

    async def _step_tool(self, step: dict, context: dict) -> dict:
        """Fuehrt ein Tool aus der bestehenden CompanionEngine aus."""
        tool_name = step.get("tool", "")
        args = step.get("args", {})

        if not tool_name:
            raise ValueError("Step 'tool': Kein Tool-Name angegeben.")

        # Template-Variablen ersetzen
        args = self._resolve_templates(args, context)

        from backend.agent_reflection import reflect_action
        from backend.security import audit_log, is_command_allowed, validate_params
        from backend.tool_registry import ToolSchemaValidationError, validate_tool_arguments

        try:
            schema_args = validate_tool_arguments(tool_name, args)
        except ToolSchemaValidationError as exc:
            audit_log(tool_name, "workflow_tool_schema_invalid", f"error={str(exc)[:200]}")
            raise PermissionError("Workflow tool arguments are invalid.")

        # Permission classification is read-only; enforcement happens after reflection.
        permission = is_command_allowed(tool_name)
        reflection = reflect_action(
            tool_name,
            schema_args,
            permission=permission,
            source="workflow",
            plan_length=int(context.get("workflow_step_count") or 1),
        )
        if reflection is not None and not reflection.should_execute:
            audit_log(tool_name, "workflow_reflection_blocked", f"reason={reflection.reason[:120]}")
            raise PermissionError("Workflow tool blocked by safety reflection.")

        if permission == "blocked":
            raise PermissionError(f"Tool '{tool_name}' ist blockiert.")
        if permission in {"confirmation_required", "unknown"}:
            raise PermissionError(f"Tool '{tool_name}' erfordert Bestaetigung und wird im Workflow nicht automatisch ausgefuehrt.")

        try:
            safe_args = validate_params(tool_name, schema_args)
        except ValueError as exc:
            audit_log(tool_name, "workflow_param_blocked", str(exc)[:200])
            raise PermissionError(str(exc))

        # Tool ausfuehren via CompanionEngine
        if self._companion_execute:
            result = await asyncio.to_thread(self._companion_execute, tool_name, safe_args)
            return result
        else:
            raise RuntimeError("CompanionEngine nicht verfuegbar. Backend noch nicht vollstaendig gestartet?")

    async def _step_ai_prompt(self, step: dict, context: dict) -> dict:
        """Sendet einen Prompt an die KI und gibt die Antwort zurueck."""
        prompt = step.get("prompt", "")
        if not prompt:
            raise ValueError("Step 'ai_prompt': Kein Prompt angegeben.")

        # Template-Variablen ersetzen
        prompt = self._resolve_template_string(prompt, context)

        try:
            from backend.ai_engine import chat
            result = await asyncio.to_thread(chat, prompt, [])
            return {
                "type": "ai_response",
                "content": result.get("content", ""),
                "prompt": prompt[:200],
            }
        except Exception as e:
            raise RuntimeError(f"AI-Prompt fehlgeschlagen: {e}")

    async def _step_condition(self, step: dict, context: dict) -> dict:
        """Wertet eine Bedingung aus und fuehrt then_steps oder else_steps aus."""
        check_expr = step.get("check", "")
        then_steps = step.get("then_steps", [])
        else_steps = step.get("else_steps", [])

        if not check_expr:
            raise ValueError("Step 'condition': Kein 'check'-Ausdruck angegeben.")

        # Template-Variablen ersetzen und Bedingung auswerten
        resolved_expr = self._resolve_template_string(check_expr, context)
        condition_met = self._evaluate_condition(resolved_expr)

        branch_name = "then" if condition_met else "else"
        branch_steps = then_steps if condition_met else else_steps

        branch_results = []
        for sub_step in branch_steps:
            sub_result = await self._execute_step(sub_step, context)
            branch_results.append(sub_result)
            context["prev_result"] = sub_result

        return {
            "type": "condition",
            "check": check_expr,
            "resolved": resolved_expr,
            "condition_met": condition_met,
            "branch": branch_name,
            "results": branch_results,
        }

    async def _step_delay(self, step: dict) -> dict:
        """Wartet eine bestimmte Anzahl Sekunden."""
        seconds = step.get("seconds", 1)
        seconds = max(0, min(seconds, 300))  # Max 5 Minuten Wartezeit
        await asyncio.sleep(seconds)
        return {"type": "delay", "waited_seconds": seconds}

    async def _step_notify(self, step: dict, context: dict) -> dict:
        """Erstellt eine Benachrichtigung (Logging + optional System-Notification)."""
        message = step.get("message", "Workflow-Benachrichtigung")
        message = self._resolve_template_string(message, context)

        logger.info(f"Workflow-Notification: {message}")

        # Versuche Windows Toast Notification
        try:
            message_b64 = base64.b64encode(message[:200].encode("utf-8")).decode("ascii")
            ps_cmd = f'''
            $message = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("{message_b64}"))
            [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
            $notify = New-Object System.Windows.Forms.NotifyIcon
            $notify.Icon = [System.Drawing.SystemIcons]::Information
            $notify.Visible = $true
            $notify.ShowBalloonTip(5000, "Lexa Workflow", $message, [System.Windows.Forms.ToolTipIcon]::Info)
            Start-Sleep -Seconds 6
            $notify.Dispose()
            '''
            await asyncio.to_thread(
                subprocess.run,
                ["powershell", "-Command", ps_cmd],
                capture_output=True, timeout=15,
            )
        except Exception as e:
            logger.debug(f"System-Notification fehlgeschlagen: {e}")

        return {"type": "notify", "message": message}

    async def _step_http(self, step: dict, context: dict) -> dict:
        """Fuehrt einen HTTP-Request aus."""
        import urllib.request
        import urllib.error

        method = step.get("method", "GET").upper()
        url = step.get("url", "")
        body = step.get("body")
        headers = step.get("headers", {})

        if not url:
            raise ValueError("Step 'http': Keine URL angegeben.")

        # Template-Variablen ersetzen
        url = self._resolve_template_string(url, context)

        # Sicherheits-Check: nur http/https
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Nur HTTP/HTTPS URLs erlaubt, nicht: {url[:50]}")

        url = _validate_workflow_http_url(url)

        # SSRF Protection: Block private IPs
        try:
            hostname = urlparse(url).hostname
            if hostname:
                resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for _, _, _, _, sockaddr in resolved:
                    ip = ipaddress.ip_address(sockaddr[0])
                    if is_dangerous_network_ip(ip):
                        raise ValueError(f"Zugriff auf private IP-Adressen nicht erlaubt: {hostname}")
        except (socket.gaierror, OSError):
            pass  # DNS resolution failed — let the request fail naturally

        # Request bauen
        body_bytes = None
        if body:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")
            elif isinstance(body, str):
                body_bytes = body.encode("utf-8")

        req = urllib.request.Request(url, data=body_bytes, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("User-Agent", "Lexa-AI-Workflow/1.0")

        try:
            def _do_request():
                opener = urllib.request.build_opener(_SafeWorkflowRedirectHandler)
                with opener.open(req, timeout=30) as resp:
                    return {
                        "status_code": resp.status,
                        "headers": dict(resp.headers),
                        "body": resp.read().decode("utf-8", errors="replace")[:10000],
                    }

            result = await asyncio.to_thread(_do_request)
            return {"type": "http", "method": method, "url": url[:200], **result}
        except urllib.error.HTTPError as e:
            return {
                "type": "http",
                "method": method,
                "url": url[:200],
                "status_code": e.code,
                "error": str(e),
            }
        except Exception as e:
            raise RuntimeError(f"HTTP-Request fehlgeschlagen: {e}")

    # ── Template-Engine ───────────────────────────

    def _resolve_templates(self, obj: Any, context: dict) -> Any:
        """Ersetzt {{prev_result}}, {{prev_result.key}} etc. rekursiv in dicts/lists/strings."""
        if isinstance(obj, str):
            return self._resolve_template_string(obj, context)
        elif isinstance(obj, dict):
            return {k: self._resolve_templates(v, context) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_templates(item, context) for item in obj]
        return obj

    def _resolve_template_string(self, text: str, context: dict) -> str:
        """Ersetzt {{variable}} und {{variable.key}} Platzhalter."""
        def _replacer(match):
            expr = match.group(1).strip()
            parts = expr.split(".")
            if len(parts) > MAX_TEMPLATE_DEPTH:
                return match.group(0)

            # Navigate context
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, (list, tuple)):
                    try:
                        value = value[int(part)]
                    except (ValueError, IndexError):
                        return match.group(0)  # Unreplaced
                else:
                    return match.group(0)

                if value is None:
                    return ""

            return str(value) if value is not None else ""

        return re.sub(r"\{\{(.+?)\}\}", _replacer, text)

    def _evaluate_condition(self, expr: str) -> bool:
        """Wertet eine einfache Bedingung aus (nur sichere Vergleiche).
        Unterstuetzt: ==, !=, >, <, >=, <=, 'contains', 'is_empty', 'not_empty'
        """
        expr = expr.strip()
        lower_expr = expr.lower()

        # Boolean keywords
        if lower_expr in ("true", "1", "yes", "ja"):
            return True
        if lower_expr in ("false", "0", "no", "nein", ""):
            return False

        # "is_empty" / "not_empty" check
        def _is_empty_value(value: str) -> bool:
            normalized = value.strip()
            return not normalized or normalized.lower() in ("none", "null")

        tokens = expr.split()
        lower_tokens = [token.lower() for token in tokens]
        if lower_tokens == ["is_empty"]:
            return True
        if lower_tokens == ["not_empty"]:
            return False
        if len(tokens) == 2:
            if lower_tokens[0] == "is_empty":
                return _is_empty_value(tokens[1])
            if lower_tokens[1] == "is_empty":
                return _is_empty_value(tokens[0])
            if lower_tokens[0] == "not_empty":
                return not _is_empty_value(tokens[1])
            if lower_tokens[1] == "not_empty":
                return not _is_empty_value(tokens[0])

        # Comparison operators
        for op in (">=", "<=", "!=", "==", ">", "<"):
            if op in expr:
                parts = expr.split(op, 1)
                if len(parts) == 2:
                    left, right = parts[0].strip(), parts[1].strip()
                    try:
                        left_num = float(left)
                        right_num = float(right)
                        if op == ">=":
                            return left_num >= right_num
                        if op == "<=":
                            return left_num <= right_num
                        if op == "!=":
                            return left_num != right_num
                        if op == "==":
                            return left_num == right_num
                        if op == ">":
                            return left_num > right_num
                        if op == "<":
                            return left_num < right_num
                    except ValueError:
                        # String comparison
                        if op == "==":
                            return left == right
                        if op == "!=":
                            return left != right
                        return False
                break

        # "contains" operator
        if " contains " in expr:
            parts = expr.split(" contains ", 1)
            if len(parts) == 2:
                return parts[1].strip().lower() in parts[0].strip().lower()

        # Fallback: truthy check
        return bool(expr)

    # ── Scheduler ─────────────────────────────────

    async def start_scheduler(self, companion_execute_fn=None) -> None:
        """Startet den Workflow-Scheduler als Background-Task."""
        self._companion_execute = companion_execute_fn

        if self._scheduler_task and not self._scheduler_task.done():
            logger.info("Workflow-Scheduler laeuft bereits")
            return

        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Workflow-Scheduler gestartet (30s Intervall)")

        # Event-Handler aus DB laden
        self._load_event_handlers()

    def _load_event_handlers(self) -> None:
        """Laedt Event-basierte Workflows und registriert sie."""
        self._event_handlers.clear()
        db = self._get_db()
        try:
            rows = db.execute(
                "SELECT id, trigger_config FROM workflows WHERE enabled = 1"
            ).fetchall()
            for row in rows:
                try:
                    trigger = json.loads(row["trigger_config"])
                    if trigger.get("type") == "event":
                        event_name = trigger.get("event", "")
                        if event_name:
                            self._event_handlers.setdefault(event_name, []).append(row["id"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if self._event_handlers:
                logger.info(f"Event-Handler geladen: {dict((k, len(v)) for k, v in self._event_handlers.items())}")
        finally:
            self._release_db(db)

    async def _scheduler_loop(self) -> None:
        """Hintergrund-Loop: Prueft alle 30s ob Schedule-Workflows faellig sind."""
        logger.info("Workflow-Scheduler-Loop gestartet")
        while True:
            try:
                await asyncio.sleep(30)

                db = self._get_db()
                try:
                    rows = db.execute(
                        "SELECT * FROM workflows WHERE enabled = 1"
                    ).fetchall()
                    workflows = [self._row_to_dict(r) for r in rows]
                finally:
                    self._release_db(db)

                now = datetime.now()
                now_str = now.strftime("%Y-%m-%d %H:%M")

                for wf in workflows:
                    trigger = wf.get("trigger", {})
                    if trigger.get("type") != "schedule":
                        continue
                    if self._workflow_in_backoff(wf, now):
                        continue

                    should_run = False

                    # Cron-basiert
                    if "cron" in trigger:
                        should_run = _cron_matches(trigger["cron"], now)

                    # Taeglich um bestimmte Uhrzeit
                    elif "daily_at" in trigger:
                        should_run = _daily_at_matches(trigger["daily_at"], now)

                    # Intervall-basiert
                    elif "interval_minutes" in trigger:
                        should_run = _interval_matches(trigger["interval_minutes"], now)

                    if not should_run:
                        continue

                    # Bereits diese Minute ausgefuehrt?
                    if wf.get("last_run"):
                        last_run_str = wf["last_run"][:16]  # "YYYY-MM-DD HH:MM"
                        if last_run_str == now_str:
                            continue

                    # Workflow ausfuehren (non-blocking)
                    logger.info(f"Scheduler: Workflow '{wf['name']}' ist faellig — wird gestartet")
                    asyncio.create_task(self._safe_run_workflow(wf["id"]))

            except asyncio.CancelledError:
                logger.info("Workflow-Scheduler gestoppt")
                break
            except Exception as e:
                logger.error(f"Scheduler-Loop Fehler: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _safe_run_workflow(self, workflow_id: str) -> None:
        """Wrapper fuer run_workflow mit Error-Handling."""
        try:
            await self.run_workflow(workflow_id)
        except Exception as e:
            logger.error(f"Workflow {workflow_id} fehlgeschlagen: {e}", exc_info=True)

    def stop_scheduler(self) -> None:
        """Stoppt den Scheduler."""
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            self._scheduler_task = None
            self._close_thread_db()
            logger.info("Workflow-Scheduler gestoppt")

    # ── Events ────────────────────────────────────

    async def emit_event(self, event_name: str, data: Optional[dict] = None) -> list[dict]:
        """Verarbeitet ein Event und startet zugehoerige Workflows.
        Gibt eine Liste der gestarteten Workflow-Ergebnisse zurueck.
        """
        data = data or {}
        handler_ids = self._event_handlers.get(event_name, [])
        if not handler_ids:
            return []

        logger.info(f"Event '{event_name}' empfangen — {len(handler_ids)} Workflow(s) registriert")
        results = []

        for wf_id in handler_ids:
            wf = self.get_workflow(wf_id)
            if not wf or not wf.get("enabled"):
                continue
            if self._workflow_in_backoff(wf):
                continue

            # Threshold-Check (z.B. CPU > 90%)
            trigger = wf.get("trigger", {})
            threshold = trigger.get("threshold")
            if threshold is not None:
                current_value = data.get("value", 0)
                try:
                    if float(current_value) < float(threshold):
                        continue
                except (ValueError, TypeError):
                    pass

            # Pfad-Check (z.B. file_changed mit path-Filter)
            trigger_path = trigger.get("path")
            if trigger_path:
                event_path = data.get("path", "")
                if not event_path.startswith(trigger_path):
                    continue

            # App-Check (z.B. app_opened mit app-Filter)
            trigger_app = trigger.get("app")
            if trigger_app:
                event_app = data.get("app", "")
                if trigger_app.lower() not in event_app.lower():
                    continue

            # Minutes-Check (z.B. idle_minutes)
            trigger_minutes = trigger.get("minutes")
            if trigger_minutes is not None:
                event_minutes = data.get("minutes", 0)
                try:
                    if float(event_minutes) < float(trigger_minutes):
                        continue
                except (ValueError, TypeError):
                    pass

            logger.info(f"Event '{event_name}' triggert Workflow '{wf['name']}'")
            result = await self.run_workflow(wf_id)
            results.append(result)

        return results

    # ── Helpers ────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Konvertiert eine SQLite-Row in ein Workflow-Dict."""
        d = dict(row)
        # JSON-Felder parsen
        if "trigger_config" in d:
            try:
                d["trigger"] = json.loads(d["trigger_config"])
            except (json.JSONDecodeError, TypeError):
                d["trigger"] = {}
            del d["trigger_config"]
        if "steps" in d and isinstance(d["steps"], str):
            try:
                d["steps"] = json.loads(d["steps"])
            except (json.JSONDecodeError, TypeError):
                d["steps"] = []
        d["enabled"] = bool(d.get("enabled", 0))
        try:
            d["failure_count"] = max(0, int(d.get("failure_count") or 0))
        except (TypeError, ValueError):
            d["failure_count"] = 0
        return d

    def get_status(self) -> dict:
        """Gibt den aktuellen Status der Workflow-Engine zurueck."""
        db = self._get_db()
        try:
            total = db.execute("SELECT COUNT(*) as c FROM workflows").fetchone()["c"]
            active = db.execute("SELECT COUNT(*) as c FROM workflows WHERE enabled = 1").fetchone()["c"]
            total_runs = db.execute("SELECT SUM(run_count) as c FROM workflows").fetchone()["c"] or 0
            last_log = db.execute(
                "SELECT finished_at, status FROM workflow_logs ORDER BY finished_at DESC LIMIT 1"
            ).fetchone()
        finally:
            self._release_db(db)

        return {
            "scheduler_running": self._scheduler_task is not None and not self._scheduler_task.done(),
            "total_workflows": total,
            "active_workflows": active,
            "total_runs": total_runs,
            "event_handlers": {k: len(v) for k, v in self._event_handlers.items()},
            "last_run": dict(last_log) if last_log else None,
        }


# ══════════════════════════════════════════════════
#  SINGLETON ACCESS
# ══════════════════════════════════════════════════

def get_workflow_engine() -> WorkflowEngine:
    """Gibt die Singleton-Instanz der WorkflowEngine zurueck."""
    return WorkflowEngine()
