"""
Build script for Lexa AI backend → standalone executable.
Usage: python build_backend.py

Creates backend-dist/lexa-backend/lexa-backend.exe (onedir mode)
which electron-builder packages into the NSIS installer.
"""

import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "backend-dist"


def main():
    # Clean previous build
    if DIST.exists():
        shutil.rmtree(DIST)

    print("[Build] Creating backend executable with PyInstaller...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", "lexa-backend",
        "--distpath", str(DIST),
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

    # The output is in backend-dist/lexa-backend/
    exe_path = DIST / "lexa-backend" / "lexa-backend.exe"
    if exe_path.exists():
        print(f"[Build] Success! Backend exe: {exe_path}")
        print(f"[Build] Size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("[Build] ERROR: exe not found after build!")
        sys.exit(1)


if __name__ == "__main__":
    main()
