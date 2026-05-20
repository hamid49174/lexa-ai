from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_backend_main_uses_lifespan_instead_of_deprecated_on_event():
    src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    assert "@app.on_event" not in src
    assert "asynccontextmanager" in src
    assert "app.router.lifespan_context = _lifespan" in src


def test_backend_lifespan_preserves_startup_and_shutdown_handlers():
    src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    assert "async def startup_event" in src
    assert "async def shutdown_event" in src
    assert "await startup_event()" in src
    assert "await shutdown_event()" in src
