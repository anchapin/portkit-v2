"""Pick a provider from config or the environment.

Precedence, highest first: explicit arguments, the ``config`` mapping (e.g. an
``[agent]`` table you loaded from TOML), then environment variables:

    PORTKIT_LLM_PROVIDER   openai | anthropic | gemini | gemini_native
    PORTKIT_LLM_MODEL      model name, required
    PORTKIT_LLM_BASE_URL   optional, for gateways and local servers
    PORTKIT_LLM_TEMPERATURE optional sampling temperature, sent as ``temperature``
    OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY   the provider's usual key variable

Two Gemini paths are available:

- ``gemini``: OpenAI-compatible endpoint at ``/v1beta/openai/chat/completions``.
  Same wire format as ``openai``. Rejects AI Studio **auth keys** with HTTP 400
  (aistudio.google.com/docs/api-key — auth keys became the default on May 28,
  2026).
- ``gemini_native``: Native ``generateContent`` endpoint at
  ``/v1beta/models/<model>:generateContent``, authenticated with
  ``X-goog-api-key``. Use this for any post-May-2026 AI Studio key, or when
  the OpenAI-compat path produces ``finish_reason=error`` against a Gemini
  model. See :mod:`portkit.agent.gemini`.

Config keys mirror those names: provider, model, base_url, api_key, and
api_key_env to read the key from a differently named variable.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from .anthropic import AnthropicClient
from .gemini import GeminiClient
from .http import Transport, post_json
from .loop import LLMClient
from .openai import GEMINI_BASE_URL, OpenAIClient

PROVIDERS = {
    "openai": (OpenAIClient, "OPENAI_API_KEY"),
    "anthropic": (AnthropicClient, "ANTHROPIC_API_KEY"),
    # OpenAI-compat endpoint. Rejects AI Studio auth keys with HTTP 400
    # (aistudio.google.com/docs/api-key). Prefer ``gemini_native`` for any
    # post-May-2026 AI Studio key.
    "gemini": (OpenAIClient, "GEMINI_API_KEY"),
    # Native ``generateContent`` endpoint. Accepts AI Studio auth keys via
    # the ``X-goog-api-key`` header. See :mod:`portkit.agent.gemini`.
    "gemini_native": (GeminiClient, "GEMINI_API_KEY"),
}
DEFAULT_BASE_URLS = {"gemini": GEMINI_BASE_URL}


def make_client(
    provider: str | None = None,
    model: str | None = None,
    *,
    config: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    transport: Transport = post_json,
) -> LLMClient:
    config = config or {}
    env = os.environ if env is None else env

    def pick(arg, key):
        return arg or config.get(key) or env.get(f"PORTKIT_LLM_{key.upper()}")

    name = (pick(provider, "provider") or "").strip().lower()
    if name not in PROVIDERS:
        raise ValueError(
            f"unknown or missing LLM provider {name!r}; set PORTKIT_LLM_PROVIDER to one of {sorted(PROVIDERS)}"
        )
    chosen_model = pick(model, "model")
    if not chosen_model:
        raise ValueError("no LLM model configured; set PORTKIT_LLM_MODEL")

    cls, default_key_env = PROVIDERS[name]
    api_key = config.get("api_key") or env.get(config.get("api_key_env") or default_key_env)
    kwargs: dict[str, Any] = {"model": chosen_model, "api_key": api_key, "transport": transport}
    base_url = pick(None, "base_url") or DEFAULT_BASE_URLS.get(name)
    if base_url:
        kwargs["base_url"] = base_url
    temperature = pick(None, "temperature")
    if temperature not in (None, ""):
        try:
            kwargs["extra"] = {"temperature": float(temperature)}
        except (TypeError, ValueError):
            raise ValueError(f"PORTKIT_LLM_TEMPERATURE must be a number, got {temperature!r}") from None
    return cls(**kwargs)
