"""
PyInstaller entry point for Lexa AI backend.
Starts the FastAPI server via uvicorn when run as a standalone exe.
"""

import sys
import os

# Ensure the parent directory is in the path so imports work
if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle
    base_path = sys._MEIPASS
    sys.path.insert(0, base_path)
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
