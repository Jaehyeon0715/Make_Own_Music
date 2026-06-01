# -*- coding: utf-8 -*-
"""Post-hoc stem separation via the Demucs CLI (run as an isolated subprocess).

Demucs is kept out of the FastAPI process on purpose: it pulls in torch and a
multi-hundred-MB model. Running it through ``python -m demucs`` mirrors how
ACE-Step is treated (an external engine) and avoids importing torch here.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# htdemucs ships 4 stems. Vocals is usually near-silent for instrumental output,
# so the default keeps only the three musical stems. Override via env if needed.
DEMUCS_MODEL = os.getenv("DEMUCS_MODEL", "htdemucs")
DEMUCS_DEVICE = os.getenv("DEMUCS_DEVICE", "cpu")  # set "cuda" when GPU is free
DEMUCS_TIMEOUT = float(os.getenv("DEMUCS_TIMEOUT", "1800"))
STEM_ORDER = [
    s.strip()
    for s in os.getenv("DEMUCS_STEMS", "drums,bass,other").split(",")
    if s.strip()
]


async def separate(input_wav: str, out_dir: str) -> list[dict]:
    """Split ``input_wav`` into stems.

    Returns ``[{"stem": name, "path": abs_path}, ...]`` in ``STEM_ORDER``.
    Raises ``FileNotFoundError`` if the input is missing and ``RuntimeError``
    on any Demucs failure (non-zero exit, timeout, or no stems produced).
    """
    in_path = Path(input_wav).resolve()
    if not in_path.exists():
        raise FileNotFoundError(str(in_path))

    work = Path(out_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)

    # --filename drops the per-track subfolder, so stems land directly in
    # <work>/<model>/<stem>.wav.
    cmd = [
        sys.executable, "-m", "demucs",
        "-n", DEMUCS_MODEL,
        "-d", DEMUCS_DEVICE,
        "-o", str(work),
        "--filename", "{stem}.{ext}",
        str(in_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=DEMUCS_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"demucs timed out after {DEMUCS_TIMEOUT:.0f}s")

    if proc.returncode != 0:
        tail = (stdout or b"").decode("utf-8", "replace")[-600:]
        raise RuntimeError(f"demucs exit {proc.returncode}: {tail}")

    model_dir = work / DEMUCS_MODEL
    results: list[dict] = []
    for stem in STEM_ORDER:
        p = model_dir / f"{stem}.wav"
        if p.exists():
            results.append({"stem": stem, "path": str(p)})

    if not results:
        raise RuntimeError(f"demucs produced no stems in {model_dir}")
    return results
