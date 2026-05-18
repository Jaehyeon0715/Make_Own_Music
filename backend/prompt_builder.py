# -*- coding: utf-8 -*-
"""Build final ACE-Step captions with BPM/key overrides."""
from __future__ import annotations

from typing import Optional


def build_caption(
    caption: str,
    locked: int,
    global_bpm: int,
    global_key: str,
    bpm_override: Optional[int] = None,
    key_override: Optional[str] = None,
) -> str:
    """Return the final text prompt sent to ACE-Step."""
    bpm = bpm_override if (locked == 0 and bpm_override) else global_bpm
    key = key_override if (locked == 0 and key_override) else global_key
    return f"{caption}, {bpm} bpm, {key}, no vocals"


def build_captions_for_session(tracks: list[dict], global_bpm: int, global_key: str) -> list[str]:
    """Build final captions for all tracks in order."""
    return [
        build_caption(
            caption=t["caption"],
            locked=t.get("locked", 1),
            global_bpm=global_bpm,
            global_key=global_key,
            bpm_override=t.get("bpm_override"),
            key_override=t.get("key_override"),
        )
        for t in tracks
    ]
