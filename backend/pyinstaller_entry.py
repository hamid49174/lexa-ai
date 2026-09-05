"""
PyInstaller entry point for Lexa AI backend.
Starts the FastAPI server via uvicorn when run as a standalone exe.
"""

import sys
import os
from pathlib import Path


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "lexa-ai"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lexa-ai"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lexa-ai"


# Ensure the parent directory is in the path so imports work
if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle
    base_path = sys._MEIPASS
    sys.path.insert(0, base_path)
    if not os.environ.get("LEXA_DATA_DIR"):
        data_dir = _default_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["LEXA_DATA_DIR"] = str(data_dir)
    os.chdir(base_path)

import uvicorn


def main():
    host = os.environ.get("LEXA_HOST", "127.0.0.1")
    port = int(os.environ.get("LEXA_PORT", "8000"))

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
