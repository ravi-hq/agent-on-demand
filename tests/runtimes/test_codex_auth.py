"""render_codex_auth_json: the pure ~/.codex/auth.json body builder."""

from __future__ import annotations

import json

import pytest

from agent_on_demand.runtimes.codex_auth import render_codex_auth_json


def test_renders_api_key_under_openai_api_key_field():
    body = render_codex_auth_json("sk-proj-abc123")
    parsed = json.loads(body)
    # The serde field Codex's loader keys off — must be exactly this name,
    # or Codex silently falls back to ChatGPT auth.
    assert parsed == {"OPENAI_API_KEY": "sk-proj-abc123"}


def test_body_is_valid_json_with_trailing_newline():
    body = render_codex_auth_json("sk-x")
    assert body.endswith("\n")
    json.loads(body)  # does not raise


def test_no_extra_fields_so_resolved_mode_is_apikey():
    # Codex infers ApiKey mode only when openai_api_key is present and no
    # ChatGPT `tokens` are. An accidental `tokens` key would flip it to
    # ChatGPT mode, so assert the body carries nothing but the key.
    parsed = json.loads(render_codex_auth_json("sk-x"))
    assert list(parsed.keys()) == ["OPENAI_API_KEY"]


@pytest.mark.parametrize("empty", ["", None])
def test_empty_key_raises(empty):
    # An empty auth.json would leave Codex in "ApiKey mode, no key" — worse
    # than not writing the file. The caller must skip the write instead.
    with pytest.raises(ValueError):
        render_codex_auth_json(empty)  # type: ignore[arg-type]
