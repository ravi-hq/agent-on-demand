"""Render Codex's ``~/.codex/auth.json`` for API-key authentication.

Extracted from `runtimes/codex.py` (like `codex_config.py`) so the JSON
body — the thing Codex's auth loader is picky about — can be
mutation-tested as a pure string-in/string-out function.

Why this file exists at all: unlike Claude Code (which reads
``ANTHROPIC_API_KEY`` straight from the process environment), the Codex
CLI's headless ``exec`` path does **not** authenticate from a bare
``OPENAI_API_KEY`` env var. Its auth precedence is

    CODEX_API_KEY env  >  ephemeral store  >  CODEX_ACCESS_TOKEN env
                       >  persistent ~/.codex/auth.json

so a plain ``OPENAI_API_KEY`` is never consulted and Codex falls through
to the ChatGPT/websocket transport with no bearer token (HTTP 401
"Missing bearer ..." against ``/v1/responses``). Writing ``auth.json``
with the key puts Codex in ApiKey mode via the persistent path, and —
because we write the file ourselves — it also overrides any stale
ChatGPT ``auth.json`` baked into the Sprite base image (which env vars
alone could not, since only ``CODEX_API_KEY`` outranks ``auth.json``).

A bare ``{"OPENAI_API_KEY": "..."}`` is exactly what ``codex login
--api-key`` historically writes; Codex's ``resolved_mode()`` infers
ApiKey when ``openai_api_key`` is present and no ChatGPT ``tokens`` are.
"""

from __future__ import annotations

import json

# The serde-renamed field Codex reads for the API key. Codex's loader keys
# off this exact name; a typo here silently drops auth back to ChatGPT mode.
_API_KEY_FIELD = "OPENAI_API_KEY"


def render_codex_auth_json(api_key: str) -> str:
    """Return the body of ``~/.codex/auth.json`` for API-key auth.

    `api_key` must be non-empty — the caller is responsible for skipping
    the write when there is no key (an empty file would put Codex into a
    broken "ApiKey mode but no key" state rather than a clean fallback).
    """
    if not api_key:
        raise ValueError("render_codex_auth_json requires a non-empty api_key")
    return json.dumps({_API_KEY_FIELD: api_key}) + "\n"
