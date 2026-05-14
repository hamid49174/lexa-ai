"""Lexa AI — Tool Health Check (Phase 40+)
Erkennt beim Start welche externen Tools verfügbar sind.
Cached Ergebnisse für die gesamte Session — keine wiederholten Checks.

Geprüft werden: Git, Docker, ffmpeg, Playwright, yt-dlp, 7z, pip-Pakete.
Der LLM bekommt nur Tools angezeigt die auch funktionieren.
"""

import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("lexa.tool_health")


@dataclass
class ToolStatus:
    """Status of an external tool."""
    name: str
    available: bool = False
    version: str = ""
    path: str = ""
    note: str = ""


# ── Global cache (built once at startup) ──
_health_cache: dict[str, ToolStatus] = {}
_health_ready = threading.Event()


def _check_binary(name: str, version_args: list[str] | None = None,
                  version_parse: str = "") -> ToolStatus:
    """Check if a binary is available on PATH and get its version."""
    path = shutil.which(name)
    if not path:
        return ToolStatus(name=name, available=False, note="nicht installiert")

    version = ""
    if version_args:
        try:
            result = subprocess.run(
                [path] + version_args,
                capture_output=True, text=True, timeout=5,
                encoding="utf-8", errors="replace",
            )
            output = (result.stdout + result.stderr).strip()
            # Extract version number from output
            if version_parse:
                import re
                match = re.search(version_parse, output)
                if match:
                    version = match.group(1) if match.lastindex else match.group(0)
            else:
                # Take first line, first ~50 chars
                version = output.split("\n")[0][:50]
        except Exception:
            pass

    return ToolStatus(name=name, available=True, version=version, path=path)


def _check_python_package(name: str) -> ToolStatus:
    """Check if a Python package is importable."""
    try:
        mod = __import__(name)
        version = getattr(mod, "__version__", getattr(mod, "VERSION", ""))
        if isinstance(version, tuple):
            version = ".".join(str(v) for v in version)
        return ToolStatus(name=name, available=True, version=str(version))
    except ImportError:
        return ToolStatus(name=name, available=False, note="pip install " + name)


def _run_health_checks() -> dict[str, ToolStatus]:
    """Run all health checks (called once at startup)."""
    checks: dict[str, ToolStatus] = {}

    # ── External binaries ──
    checks["git"] = _check_binary("git", ["--version"], r"(\d+\.\d+\.\d+)")
    checks["docker"] = _check_binary("docker", ["--version"], r"(\d+\.\d+\.\d+)")
    checks["ffmpeg"] = _check_binary("ffmpeg", ["-version"], r"(\d+\.\d+[\.\d]*)")
    checks["yt-dlp"] = _check_binary("yt-dlp", ["--version"], r"(\d{4}\.\d+\.\d+)")
    checks["7z"] = _check_binary("7z", [], None)

    # ── Python packages ──
    checks["playwright"] = _check_python_package("playwright")
    checks["trafilatura"] = _check_python_package("trafilatura")
    checks["rapidfuzz"] = _check_python_package("rapidfuzz")
    checks["pycaw"] = _check_python_package("pycaw")
    checks["pillow"] = _check_python_package("PIL")
    checks["pypdf"] = _check_python_package("pypdf")
    checks["httpx"] = _check_python_package("httpx")

    # ── Playwright browser binaries ──
    if checks["playwright"].available:
        try:
            import subprocess as _sp
            result = _sp.run(
                ["playwright", "install", "--dry-run", "chromium"],
                capture_output=True, text=True, timeout=10,
            )
            # If dry-run succeeds without "not installed", browsers are ready
            if result.returncode == 0:
                checks["playwright_browser"] = ToolStatus(
                    name="playwright_browser", available=True, note="Chromium ready"
                )
            else:
                checks["playwright_browser"] = ToolStatus(
                    name="playwright_browser", available=False,
                    note="Run: playwright install chromium"
                )
        except Exception:
            checks["playwright_browser"] = ToolStatus(
                name="playwright_browser", available=False,
                note="Konnte Playwright-Browser nicht prüfen"
            )

    return checks


def _build_cache() -> None:
    """Build health cache in background."""
    global _health_cache
    try:
        _health_cache = _run_health_checks()
        available = [k for k, v in _health_cache.items() if v.available]
        missing = [k for k, v in _health_cache.items() if not v.available]
        logger.info(f"Tool health: {len(available)} available, {len(missing)} missing")
        if missing:
            logger.info(f"Missing tools: {', '.join(missing)}")
    except Exception as e:
        logger.error(f"Health check failed: {e}")
    finally:
        _health_ready.set()


# ══════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════

def is_available(tool_name: str) -> bool:
    """Check if a specific tool is available. Non-blocking after init."""
    _health_ready.wait(timeout=10)
    status = _health_cache.get(tool_name)
    return status.available if status else False


def get_status(tool_name: str) -> Optional[ToolStatus]:
    """Get detailed status of a tool."""
    _health_ready.wait(timeout=10)
    return _health_cache.get(tool_name)


def get_all_status() -> dict[str, ToolStatus]:
    """Get status of all checked tools."""
    _health_ready.wait(timeout=10)
    return dict(_health_cache)


def get_health_summary() -> dict:
    """Get a JSON-serializable health summary (for API/frontend)."""
    _health_ready.wait(timeout=10)
    tools = {}
    for name, status in _health_cache.items():
        tools[name] = {
            "available": status.available,
            "version": status.version,
            "note": status.note,
        }
    available = sum(1 for s in _health_cache.values() if s.available)
    total = len(_health_cache)
    return {
        "tools": tools,
        "available_count": available,
        "total_count": total,
        "health_pct": round(available / total * 100) if total else 0,
    }


def get_missing_tools() -> list[str]:
    """Return names of tools that are NOT available."""
    _health_ready.wait(timeout=10)
    return [name for name, status in _health_cache.items() if not status.available]


def get_available_tools() -> list[str]:
    """Return names of tools that ARE available."""
    _health_ready.wait(timeout=10)
    return [name for name, status in _health_cache.items() if status.available]


def refresh() -> None:
    """Force re-check of all tools (e.g., after user installs something)."""
    global _health_cache
    _health_ready.clear()
    _health_cache = _run_health_checks()
    _health_ready.set()


# ══════════════════════════════════════════════════
#  INIT — Background check on import
# ══════════════════════════════════════════════════

def init_async() -> None:
    """Start health checks in background thread (non-blocking)."""
    t = threading.Thread(target=_build_cache, daemon=True, name="tool-health")
    t.start()


# Auto-start on import
init_async()
