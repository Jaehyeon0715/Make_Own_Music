# -*- coding: utf-8 -*-
"""Async HTTP client for the ACE-Step API (OpenRouter-compatible /v1/chat/completions)."""
from __future__ import annotations

import asyncio
import base64
import os
from typing import List, Optional

import httpx

ACESTEP_URL = os.getenv("ACESTEP_URL", "http://localhost:8001")
# Default 30 min — CPU VAE fallback on low-VRAM systems can take very long.
_TIMEOUT = float(os.getenv("ACESTEP_CLIENT_TIMEOUT", "1800"))
_CONNECT_TIMEOUT = 10.0

_cached_model_id: Optional[str] = None


# ── Low-level helpers ─────────────────────────────────────────────────────────

async def _get(path: str, timeout: float = 30.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(f"{ACESTEP_URL}{path}")
        if r.status_code >= 400:
            raise RuntimeError(f"ACE-Step GET {path} -> {r.status_code}: {r.text[:400]}")
        return r.json()


async def _post(path: str, payload: dict, timeout: float = _TIMEOUT) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(f"{ACESTEP_URL}{path}", json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"ACE-Step POST {path} -> {r.status_code}: {r.text[:400]}")
        return r.json()


def _save(data: bytes, path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _decode_audio(response: dict) -> bytes:
    """Extract and base64-decode audio from an OpenRouter chat completion response."""
    choices = response.get("choices", [])
    if not choices:
        raise ValueError("ACE-Step response has no choices")

    msg = choices[0].get("message", {})
    audio = msg.get("audio")
    if not audio:
        raise ValueError("ACE-Step response has no audio in message")

    audio_url: str = audio[0].get("audio_url", {}).get("url", "")
    if not audio_url.startswith("data:"):
        raise ValueError(f"Unexpected audio_url format: {audio_url[:80]}")

    # "data:audio/wav;base64,<data>"
    b64_part = audio_url.split(",", 1)[1]
    return base64.b64decode(b64_part)


async def _get_model_id() -> str:
    """Return the active model ID, resolved from /health on first call."""
    global _cached_model_id
    if _cached_model_id:
        return _cached_model_id

    # Explicit env override wins.
    override = os.getenv("ACESTEP_MODEL")
    if override:
        _cached_model_id = override if "/" in override else f"acestep/{override}"
        return _cached_model_id

    try:
        data = await _get("/health", timeout=_CONNECT_TIMEOUT)
        # wrap_response may nest data under "data" key
        payload = data.get("data", data)
        model = payload.get("loaded_model", "")
        if model:
            _cached_model_id = f"acestep/{model}"
            return _cached_model_id
    except Exception:
        pass
    # Final fallback — most installs ship with the turbo checkpoint.
    _cached_model_id = "acestep/acestep-v15-turbo"
    return _cached_model_id


def _text_message(caption: str) -> dict:
    return {"role": "user", "content": f"<prompt>{caption}</prompt>"}


def _multimodal_message(caption: str, audio_b64_list: List[str]) -> dict:
    """Build a user message with text prompt + one or more base64 WAV parts."""
    parts: list = [{"type": "text", "text": f"<prompt>{caption}</prompt>"}]
    for b64 in audio_b64_list:
        parts.append(
            {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}}
        )
    return {"role": "user", "content": parts}


# ── Public API ────────────────────────────────────────────────────────────────

async def health_check() -> bool:
    """Return True when the ACE-Step server is up and a model is initialized."""
    try:
        data = await _get("/health", timeout=_CONNECT_TIMEOUT)
        payload = data.get("data", data)
        return payload.get("status") == "ok"
    except Exception:
        return False


async def text2music(
    caption: str,
    duration: float,
    output_path: str,
) -> str:
    """Generate first track from text caption only (no reference audio)."""
    model = await _get_model_id()
    payload = {
        "model": model,
        "messages": [_text_message(caption)],
        "task_type": "text2music",
        "lyrics": "[inst]",
        "audio_config": {
            "duration": duration,
            "format": "wav",
            "instrumental": True,
        },
        "stream": False,
    }
    resp = await _post("/v1/chat/completions", payload)
    _save(_decode_audio(resp), output_path)
    return output_path


async def track_addition(
    caption: str,
    duration: float,
    ref_audio_paths: List[str],
    output_path: str,
) -> str:
    """Generate a track that complements existing tracks (reference-guided text2music).

    Sends the first reference track as input_audio so ACE-Step can match style/BPM.
    """
    model = await _get_model_id()

    if ref_audio_paths:
        with open(ref_audio_paths[0], "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        message = _multimodal_message(caption, [b64])
    else:
        message = _text_message(caption)

    payload = {
        "model": model,
        "messages": [message],
        "task_type": "text2music",
        "lyrics": "[inst]",
        "audio_config": {
            "duration": duration,
            "format": "wav",
            "instrumental": True,
        },
        "stream": False,
    }
    resp = await _post("/v1/chat/completions", payload)
    _save(_decode_audio(resp), output_path)
    return output_path


async def repaint(
    caption: str,
    audio_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> str:
    """Regenerate only the [start_sec, end_sec] region of an existing track."""
    model = await _get_model_id()

    with open(audio_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": model,
        "messages": [_multimodal_message(caption, [b64])],
        "task_type": "repaint",
        "lyrics": "[inst]",
        "repainting_start": start_sec,
        "repainting_end": end_sec,
        "audio_config": {
            "format": "wav",
            "instrumental": True,
        },
        "stream": False,
    }
    resp = await _post("/v1/chat/completions", payload)
    _save(_decode_audio(resp), output_path)
    return output_path
