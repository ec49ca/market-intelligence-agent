"""One-shot LLM completion. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env."""

from __future__ import annotations

import json
import os
import re

import httpx

from llm.paths import ROOT

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


class LLMConfigError(RuntimeError):
    pass


def _headers_anthropic(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def complete(system: str, user: str, *, max_tokens: int = 4000) -> str:
    """Return assistant text. Prefers Anthropic, then OpenAI."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if anthropic_key:
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers=_headers_anthropic(anthropic_key),
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=120.0,
        )
        response.raise_for_status()
        blocks = response.json().get("content") or []
        return "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
    if openai_key:
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    raise LLMConfigError(
        "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env (see .env.example)"
    )


def parse_json_object(text: str) -> dict:
    """Pull a JSON object out of a model reply (fences allowed)."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.S)
    blob = fenced.group(1) if fenced else stripped
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM did not return a JSON object")
    return json.loads(blob[start : end + 1])
