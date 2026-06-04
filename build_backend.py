"""
Build script for Lexa AI backend → standalone executable.
Usage: python build_backend.py

Creates backend-dist/lexa-backend/lexa-backend.exe (onedir mode)
which electron-builder packages into the NSIS installer.
"""

import subprocess
import sys
import shutil
import os
import stat
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "backend-dist"
BUILD = ROOT / "build"
BACKEND_BUNDLE = DIST / "lexa-backend"
FORBIDDEN_BACKEND_RUNTIME_ARTIFACTS = {
    "audit.log",
    "bridge-audit.log",
    "lexa_memory.db",
    "lexa_memory.db-shm",
    "lexa_memory.db-wal",
}


def _assert_build_dist_path_safe(path: Path) -> None:
    root = ROOT.resolve()
    resolved = path.resolve()
    if resolved.parent != root or resolved.name != "backend-dist":
        raise RuntimeError(f"Refusing to clean unexpected build output path: {resolved}")


def _make_writable_and_retry(function, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except OSError:
        pass
    function(path)


def remove_build_dist_tree(path: Path = DIST) -> None:
    _assert_build_dist_path_safe(path)
    if not path.exists():
        return
    try:
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    except TypeError:
        shutil.rmtree(path, onerror=_make_writable_and_retry)
    except Exception as exc:
        raise RuntimeError(
            "Unable to clean backend-dist. Close running Lexa/backend processes, "
            "pause OneDrive sync if it is locking packaged files, then retry."
        ) from exc


def _assert_backend_bundle_path_safe(path: Path) -> None:
    if path.resolve() != BACKEND_BUNDLE.resolve():
        raise RuntimeError(f"Refusing to clean unexpected backend bundle path: {path.resolve()}")


def remove_forbidden_backend_runtime_artifacts(bundle_dir: Path = BACKEND_BUNDLE) -> list[Path]:
    _assert_backend_bundle_path_safe(bundle_dir)
    removed: list[Path] = []
    if not bundle_dir.exists():
        return removed

    for candidate in bundle_dir.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.name not in FORBIDDEN_BACKEND_RUNTIME_ARTIFACTS:
            continue
        candidate.unlink()
        removed.append(candidate)
    return removed


def main():
    # Clean previous build
    try:
        remove_build_dist_tree(DIST)
    except RuntimeError as exc:
        print(f"[Build] ERROR: {exc}")
        sys.exit(1)
    BUILD.mkdir(exist_ok=True)

    print("[Build] Creating backend executable with PyInstaller...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", "lexa-backend",
        "--distpath", str(DIST),
        "--specpath", str(BUILD),
        # Hidden imports that PyInstaller misses
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "uvicorn.lifespan.off",
        "--hidden-import", "backend.main",
        "--hidden-import", "backend.ai_engine",
        "--hidden-import", "backend.memory",
        "--hidden-import", "backend.productivity",
        "--hidden-import", "backend.security",
        "--hidden-import", "backend.action_parser",
        "--hidden-import", "backend.router_companion",
        "--hidden-import", "backend.router_voice",
        "--hidden-import", "backend.router_productivity",
        "--hidden-import", "companion.engine",
        "--hidden-import", "companion.browser",
        "--hidden-import", "companion.file_tools",
        "--hidden-import", "companion.media",
        "--hidden-import", "companion.communication",
        "--hidden-import", "companion.system_tools",
        "--hidden-import", "companion.dev_tools",
        "--hidden-import", "voice.tts",
        "--hidden-import", "voice.stt",
        # Data files
        "--add-data", f"{ROOT / 'command_whitelist.json'};.",
        # Entrypoint
        str(ROOT / "backend" / "pyinstaller_entry.py"),
    ]

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("[Build] PyInstaller failed!")
        sys.exit(1)

    removed_runtime_artifacts = remove_forbidden_backend_runtime_artifacts()
    if removed_runtime_artifacts:
        print(f"[Build] Removed runtime artifacts from backend bundle: {len(removed_runtime_artifacts)}")

    # The output is in backend-dist/lexa-backend/
    exe_path = BACKEND_BUNDLE / "lexa-backend.exe"
    if exe_path.exists():
        print(f"[Build] Success! Backend exe: {exe_path}")
        print(f"[Build] Size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("[Build] ERROR: exe not found after build!")
        sys.exit(1)


if __name__ == "__main__":
    main()
