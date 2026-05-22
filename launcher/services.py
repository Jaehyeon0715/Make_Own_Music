# -*- coding: utf-8 -*-
"""Background process management for ACE-Step, Ollama, FastAPI."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import psutil
import requests

from . import config


# CREATE_NO_WINDOW flag on Windows hides any console window for the child.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class Service:
    """A single background subprocess + its log file."""

    def __init__(self, name: str, cmd: list[str], cwd: Optional[Path] = None, env: Optional[dict] = None):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.proc: Optional[subprocess.Popen] = None
        self.log_path: Path = config.LOG_DIR / f"{name}.log"

    def start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return  # already running
        log_file = open(self.log_path, "ab")
        env = os.environ.copy()
        if self.env:
            env.update(self.env)
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=str(self.cwd) if self.cwd else None,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
        )

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            parent = psutil.Process(self.proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        self.proc = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


# ── Health helpers ────────────────────────────────────────────────────────────

def wait_for_http(url: str, timeout: int, interval: float = 2.0) -> bool:
    """Poll a URL until it returns 2xx or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


def acestep_models_initialized() -> bool:
    try:
        r = requests.get(f"{config.ACESTEP_URL}/health", timeout=3)
        if r.status_code != 200:
            return False
        data = r.json()
        payload = data.get("data", data)
        return bool(payload.get("models_initialized", False))
    except Exception:
        return False


def init_acestep_model(timeout: int = config.INIT_TIMEOUT_SEC) -> bool:
    """POST /v1/init then poll until models_initialized becomes True."""
    if acestep_models_initialized():
        return True
    try:
        requests.post(
            f"{config.ACESTEP_URL}/v1/init",
            json={},
            timeout=10,
        )
    except requests.RequestException:
        # The init call itself blocks for a long time; ignore disconnects and poll.
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if acestep_models_initialized():
            return True
        time.sleep(config.HEALTH_POLL_SEC)
    return False


# ── Service factories ────────────────────────────────────────────────────────

def make_acestep() -> Service:
    return Service(
        name="acestep",
        cmd=[config.UV_PATH, "run", "acestep-api"],
        cwd=config.ACE_STEP_DIR,
    )


def make_ollama() -> Service:
    return Service(
        name="ollama",
        cmd=[config.OLLAMA_EXE, "serve"],
    )


def make_fastapi() -> Service:
    py = sys.executable  # works both dev (python.exe) and bundled
    return Service(
        name="fastapi",
        cmd=[py, "-m", "uvicorn", "backend.main:app", "--port", str(config.FASTAPI_PORT)],
        cwd=config.PROJECT_ROOT,
    )
