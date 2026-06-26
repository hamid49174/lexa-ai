"""Shared test fixtures for Lexa AI test suite."""

import gc
import shutil
import time
import uuid
from pathlib import Path

import pytest


_TEST_TMP_ROOT = Path(__file__).resolve().parent.parent / ".test-tmp"


def _remove_tree(path: Path, attempts: int = 5) -> None:
    for _ in range(attempts):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
            return
        except OSError:
            gc.collect()
            time.sleep(0.05)
    shutil.rmtree(path, ignore_errors=True)


def pytest_sessionstart(session):
    _remove_tree(_TEST_TMP_ROOT)


def pytest_sessionfinish(session, exitstatus):
    _remove_tree(_TEST_TMP_ROOT)


@pytest.fixture
def tmp_path():
    """Provide a writable temp directory on Windows/Python setups with strict ACLs."""
    _TEST_TMP_ROOT.mkdir(exist_ok=True)
    path = _TEST_TMP_ROOT / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        _remove_tree(path)


@pytest.fixture
def disable_rate_limit(monkeypatch):
    """Disable rate limiting for endpoint tests.

    Router-Module binden die Funktion via `from backend.security import check_rate_limit`,
    halten also eine EIGENE Referenz auf das urspruengliche Funktionsobjekt — ein
    `setattr(sec, "check_rate_limit", ...)` erreicht sie nicht. Darum zusaetzlich den
    GETEILTEN Zustand neutralisieren, den die echte Funktion liest (riesige Caps +
    geleerte Buckets); das wirkt unabhaengig davon, ueber welche Referenz aufgerufen wird.
    Sonst saturiert in der vollen Suite ein globaler Bucket und Endpoint-Tests bekommen 429.
    """
    import backend.security as sec
    monkeypatch.setattr(sec, "check_rate_limit", lambda *a, **kw: True)
    for bucket in sec._RATE_LIMITS.values():
        monkeypatch.setitem(bucket, "max", 10 ** 9)
        bucket["timestamps"].clear()
    for bucket in getattr(sec, "_ACTION_RATE_LIMITS", {}).values():
        monkeypatch.setitem(bucket, "max", 10 ** 9)
        bucket["entries"].clear()


@pytest.fixture
def isolate_productivity_db(tmp_path, monkeypatch):
    """Redirect productivity DB to temp database."""
    import backend.productivity as prod

    tl = prod._thread_local
    old_db = getattr(tl, "db", None)
    if old_db:
        try:
            old_db.close()
        except Exception:
            pass
        tl.db = None

    tmp_db = tmp_path / "test_prod.db"
    monkeypatch.setattr(prod, "DB_PATH", tmp_db)
    monkeypatch.setattr(prod, "_tables_ready", False)
    yield
    old_db2 = getattr(tl, "db", None)
    if old_db2:
        try:
            old_db2.close()
        except Exception:
            pass
        tl.db = None
