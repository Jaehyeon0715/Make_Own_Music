# -*- coding: utf-8 -*-
"""Global AI provider factory."""
from __future__ import annotations

import os
from typing import Optional

from .base import BaseProvider

_current_provider: Optional[BaseProvider] = None


def get_provider() -> BaseProvider:
    global _current_provider
    if _current_provider is None:
        name = os.getenv("AI_PROVIDER", "ollama")
        _current_provider = _create(name)
    return _current_provider


def switch_provider(name: str) -> BaseProvider:
    global _current_provider
    _current_provider = _create(name)
    return _current_provider


def _create(name: str) -> BaseProvider:
    name = name.lower()
    if name == "claude":
        from .claude_provider import ClaudeProvider
        return ClaudeProvider()
    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider()
    if name == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider()
    raise ValueError(f"Unsupported provider: {name}")
