# -*- coding: utf-8 -*-
"""Anthropic Claude provider implementation."""

import json
import os
import re
from typing import Optional

from .base import FALLBACK_RESULT, BaseProvider, PlanResult


class ClaudeProvider(BaseProvider):
    def __init__(self):
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=os.getenv("CLAUDE_API_KEY"))

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
                msg = await self._client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = msg.content[0].text
                return self._parse(raw, bpm, key)
            except Exception as e:
                if attempt == 2:
                    print(f"[ClaudeProvider] using fallback: {e}")
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
