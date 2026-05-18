# -*- coding: utf-8 -*-
"""Base AI provider interface and shared Pydantic models."""

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class TrackSpec(BaseModel):
    name: str
    instrument: str
    caption: str


class PlanResult(BaseModel):
    tracks: list[TrackSpec]
    bpm: int
    bpm_auto: bool
    key: str
    key_auto: bool


FALLBACK_RESULT = PlanResult(
    tracks=[
        TrackSpec(name="Drums", instrument="drums", caption="steady acoustic drums, moderate tempo"),
        TrackSpec(name="Bass", instrument="bass", caption="simple bass line, root notes"),
        TrackSpec(name="Piano", instrument="piano", caption="simple chord accompaniment, piano"),
    ],
    bpm=90,
    bpm_auto=True,
    key="C major",
    key_auto=True,
)


class BaseProvider(ABC):
    @abstractmethod
    async def plan_tracks(
        self,
        genre: str,
        mood: str,
        bpm: Optional[int],
        key: Optional[str],
        duration: int,
        prompt: str = "",
    ) -> PlanResult:
        """Return a validated track plan. Implementations should fallback on repeated failure."""
        ...

    def _build_prompt(
        self,
        genre: str,
        mood: str,
        bpm: Optional[int],
        key: Optional[str],
        duration: int,
        prompt: str,
    ) -> str:
        bpm_str = str(bpm) if bpm else "auto"
        key_str = key if key else "auto"
        return f"""You are a music composition assistant.
Suggest a multi-track instrumental composition based on the following:

Genre: {genre}
Mood: {mood}
BPM: {bpm_str}
Key: {key_str}
Duration: {duration} seconds
Additional notes: {prompt}

Respond ONLY with valid JSON in this exact format:
{{
  "tracks": [
    {{"name": "TrackName", "instrument": "instrument_id", "caption": "detailed prompt for ACE-Step"}}
  ],
  "bpm": <integer>,
  "bpm_auto": <true if you chose BPM, false if user specified>,
  "key": "<key signature>",
  "key_auto": <true if you chose key, false if user specified>
}}

Rules:
- 2 to 8 tracks
- caption must be descriptive and suitable for AI music generation
- No vocals, instrumental only
- caption must end with ", no vocals"
"""
