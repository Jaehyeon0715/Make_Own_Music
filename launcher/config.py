# -*- coding: utf-8 -*-
"""Launcher configuration — paths, ports, command lines."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# When frozen by PyInstaller, sys._MEIPASS points to the bundled assets dir.
# Otherwise repo root is two levels up from this file.
def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        # exe lives in MOM/ or wherever user placed it
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Allow per-user override of ACE-Step path via env or default to a fixed location.
ACE_STEP_DIR = Path(os.getenv("ACE_STEP_DIR", r"C:\Users\heo01\ace-step"))
UV_PATH = os.getenv("UV_PATH", r"C:\Users\heo01\.local\bin\uv.exe")
OLLAMA_EXE = os.getenv("OLLAMA_EXE", "ollama")

# Service endpoints
ACESTEP_URL = "http://localhost:8001"
OLLAMA_URL = "http://localhost:11434"
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8080"))
FASTAPI_URL = f"http://localhost:{FASTAPI_PORT}"

# Poll intervals (seconds)
HEALTH_POLL_SEC = 3
HEALTH_TIMEOUT_SEC = 60
INIT_TIMEOUT_SEC = 600  # GPU model load
