# -*- coding: utf-8 -*-
"""Google Gemini provider implementation."""

import json
import os
import re
from typing import Optional

from .base import FALLBACK_RESULT, BaseProvider, PlanResult


class GeminiProvider(BaseProvider):
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self._model = genai.GenerativeModel("gemini-1.5-flash")

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
                resp = await self._model.generate_content_async(user_prompt)
                return self._parse(resp.text, bpm, key)
            except Exception as e:
                if attempt == 2:
                    print(f"[GeminiProvider] using fallback: {e}")
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
