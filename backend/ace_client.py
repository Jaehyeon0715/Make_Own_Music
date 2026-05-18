# -*- coding: utf-8 -*-
"""Async HTTP client for the ACE-Step API."""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx

ACESTEP_URL = os.getenv("ACESTEP_URL", "http://localhost:8001")
_RETRY = 3
_TIMEOUT = 300.0  # Music generation can take several minutes.


async def _request_with_retry(
    method: str,
    path: str,
    **kwargs,
) -> bytes:
    """Run an HTTP request with exponential backoff and return response bytes."""
    url = f"{ACESTEP_URL}{path}"
    last_err: Optional[Exception] = None

    for attempt in range(_RETRY):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            last_err = e
            if attempt < _RETRY - 1:
                await asyncio.sleep(2 ** attempt)
    raise ConnectionError(f"ACE-Step request failed after {_RETRY} attempts: {last_err}")


async def health_check() -> bool:
    """Return True when the ACE-Step server responds to /health."""
    try:
        await _request_with_retry("GET", "/health")
        return True
    except Exception:
        return False


async def text2music(
    caption: str,
    duration: float,
    output_path: str,
) -> str:
    """Generate the first WAV track from text."""
    data = await _request_with_retry(
        "POST",
        "/generate",
        json={
            "task": "text2music",
            "caption": caption,
            "duration": duration,
        },
    )
    _save(data, output_path)
    return output_path


async def track_addition(
    caption: str,
    duration: float,
    ref_audio_paths: list[str],
    output_path: str,
) -> str:
    """Generate a new track while referencing previously generated WAV files."""
    files = []
    opened = []
    try:
        for i, path in enumerate(ref_audio_paths):
            f = open(path, "rb")
            opened.append(f)
            files.append(("ref_audios", (f"track_{i + 1}.wav", f, "audio/wav")))

        data = await _request_with_retry(
            "POST",
            "/generate",
            data={
                "task": "track_addition",
                "caption": caption,
                "duration": str(duration),
            },
            files=files,
        )
    finally:
        for f in opened:
            f.close()

    _save(data, output_path)
    return output_path


async def repaint(
    caption: str,
    audio_path: str,
    start_sec: float,
    end_sec: float,
    output_path: str,
) -> str:
    """Regenerate only the selected section of a track."""
    with open(audio_path, "rb") as f:
        data = await _request_with_retry(
            "POST",
            "/generate",
            data={
                "task": "repaint",
                "caption": caption,
                "start_sec": str(start_sec),
                "end_sec": str(end_sec),
            },
            files={"audio": ("track.wav", f, "audio/wav")},
        )
    _save(data, output_path)
    return output_path


def _save(data: bytes, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
