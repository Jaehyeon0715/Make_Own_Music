# -*- coding: utf-8 -*-
"""OpenAI provider implementation."""

import json
import os
import re
from typing import Optional

from .base import FALLBACK_RESULT, BaseProvider, PlanResult


class OpenAIProvider(BaseProvider):
    def __init__(self):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
                resp = await self._client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": user_prompt}],
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content
                return self._parse(raw, bpm, key)
            except Exception as e:
                if attempt == 2:
                    print(f"[OpenAIProvider] using fallback: {e}")
                    return FALLBACK_RESULT
        return FALLBACK_RESULT

    def _parse(self, raw: str, bpm, key) -> PlanResult:
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
