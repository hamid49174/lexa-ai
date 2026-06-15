"""Run-Persistenz fuer den Orchestrator (Phase 48 C).

JSON-File-Store (Muster aus os_agent_runtime) — bewusst KEINE parallelen SQLite-Writes,
da mehrere Sub-Agenten/Laeufe gleichzeitig schreiben koennten. Ein Lauf = eine JSON-Datei
unter LEXA_DATA_DIR/orchestrator_runs/<run_id>.json. Thread-safe ueber einen RLock,
atomar via os.replace. Aelteste Laeufe werden gekappt.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

from backend.agent_protocol import utc_now_iso
from backend.config import LEXA_DATA_DIR

logger = logging.getLogger("lexa.orchestrator.store")

_LOCK = threading.RLock()
_MAX_RUNS = 200
_MAX_EVENTS = 500
_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")

_SUMMARY_FIELDS = (
    "run_id", "status", "mode", "goal", "created_at", "updated_at",
    "subagent_count", "partial", "elapsed_seconds",
)


def runs_root() -> Path:
    root = Path(LEXA_DATA_DIR) / "orchestrator_runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_id(run_id: str) -> str:
    return _ID_RE.sub("", str(run_id or ""))[:64]


def _run_path(run_id: str) -> Path:
    return runs_root() / f"{_safe_id(run_id)}.json"


def save_run(run: dict) -> bool:
    """Persistiere/aktualisiere einen Lauf. Gibt True bei Erfolg zurueck."""
    run_id = _safe_id(run.get("run_id", "") if isinstance(run, dict) else "")
    if not run_id:
        return False
    payload = dict(run)
    payload["run_id"] = run_id
    payload.setdefault("created_at", utc_now_iso())
    payload["updated_at"] = utc_now_iso()
    events = payload.get("events")
    if isinstance(events, list) and len(events) > _MAX_EVENTS:
        payload["events"] = events[-_MAX_EVENTS:]
    with _LOCK:
        try:
            path = _run_path(run_id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
            os.replace(tmp, path)
            _prune_locked()
            return True
        except OSError as exc:
            logger.error("orchestrator store save failed: %s", exc)
            return False


def get_run(run_id: str) -> Optional[dict]:
    with _LOCK:
        path = _run_path(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("orchestrator store read failed: %s", exc)
            return None


def list_runs(limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), _MAX_RUNS))
    with _LOCK:
        items: list[dict] = []
        for path in runs_root().glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items.append({key: data.get(key) for key in _SUMMARY_FIELDS})
        items.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
        return items[:limit]


def _prune_locked() -> None:
    try:
        files = sorted(runs_root().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for path in files[_MAX_RUNS:]:
        try:
            path.unlink()
        except OSError:
            pass
