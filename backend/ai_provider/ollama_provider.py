# -*- coding: utf-8 -*-
"""Ollama local LLM provider implementation."""

import json
import os
import re
from typing import Optional

import httpx

from .base import FALLBACK_RESULT, BaseProvider, PlanResult

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


class OllamaProvider(BaseProvider):
    async def plan_tracks(
        self,
        genre: str,
        mood: str,
        bpm: Optional[int],
        key: Optional[str],
        duration: int,
        prompt: str = "",
    ) -> PlanResult:
        user_prompt = self._build_prompt(genre, mood, bpm, key, duration, prompt)

        for attempt in range(3):
            try:
                raw = await self._call_ollama(user_prompt)
                return self._parse(raw, bpm, key)
            except Exception as e:
                if attempt == 2:
                    print(f"[OllamaProvider] using fallback: {e}")
                    return FALLBACK_RESULT
        return FALLBACK_RESULT

    async def _call_ollama(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.7},
                },
            )
            resp.raise_for_status()
            return resp.json()["response"]

    def _parse(self, raw: str, bpm: Optional[int], key: Optional[str]) -> PlanResult:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError("JSON object not found")
        data = json.loads(match.group())

        if bpm:
            data["bpm"] = bpm
            data["bpm_auto"] = False
        if key:
            data["key"] = key
            data["key_auto"] = False

        return PlanResult(**data)
