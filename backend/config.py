from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = Path(__file__).resolve().parent.parent


# Keep env parsing forgiving so local .env mistakes do not stop startup.
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw:
        return ["http://localhost:8000", "http://127.0.0.1:8000"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except json.JSONDecodeError:
        pass
    return [x.strip() for x in raw.split(",") if x.strip()]


# Shared runtime settings. Paths resolve from the project root by default.
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")
API_KEY = os.getenv("API_KEY", "")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "sessions.db"))
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", str(BASE_DIR / "outputs"))).resolve()
FRONTEND_DIR = BASE_DIR / "frontend"
SESSION_TTL_HOURS = _env_int("SESSION_TTL_HOURS", 24)
MAX_MIX_VERSIONS = _env_int("MAX_MIX_VERSIONS", 10)
CORS_ORIGINS = _cors_origins()


def configure_cors(app) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# API key auth is optional for local use. Set API_KEY to enforce X-API-Key.
async def require_api_key(x_api_key: Annotated[Optional[str], Header()] = None) -> None:
    if not API_KEY or API_KEY == "your-secret-key-here":
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
