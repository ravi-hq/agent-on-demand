from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from agent_on_demand.runtimes.codex_auth import render_codex_auth_json
from agent_on_demand.runtimes.codex_command import build_codex_command
from agent_on_demand.runtimes.codex_config import render_codex_mcp_config

if TYPE_CHECKING:
    from agent_on_demand.session_service.backends import SessionHandle
    from agent_on_demand.session_service.specs import McpServerSpec, SessionSpec


# Codex's home on the Sprite. Auth and MCP config both live here; the dir is
# pre-created by the provision script (see post_script_dirs.py).
CODEX_HOME = "/home/sprite/.codex"
CODEX_AUTH_PATH = f"{CODEX_HOME}/auth.json"
CODEX_CONFIG_PATH = f"{CODEX_HOME}/config.toml"


def _openai_api_key(spec: "SessionSpec") -> str | None:
    """Resolve the OpenAI API key for the session.

    Mirrors the env-file precedence (session-scoped secrets override
    reusable Environment config): `secret_env_vars` first, then the
    Environment's `env_vars`. Returns None when neither carries a key.
    """
    secret = (getattr(spec, "secret_env_vars", None) or {}).get("OPENAI_API_KEY")
    if secret:
        return secret
    env = spec.environment
    if env is not None:
        return (env.env_vars or {}).get("OPENAI_API_KEY") or None
    return None


class CodexRuntime:
    """Runtime for OpenAI's Codex CLI."""

    name = "codex"
    providers: set[str] = {"openai"}
    skills_root: str | None = "/home/sprite/.codex/skills"
    skills_sh_agent: str | None = "codex"

    def install(self, handle: "SessionHandle") -> None:
        return None

    def build_command(self, spec: "SessionSpec", mode: Literal["run", "continue"]) -> list[str]:
        return build_codex_command(spec, mode)

    def write_config(
        self,
        handle: "SessionHandle",
        spec: "SessionSpec",
        mcp_servers: list["McpServerSpec"],
    ) -> None:
        # Auth first: Codex's headless `exec` path won't authenticate from a
        # bare OPENAI_API_KEY env var, so we write ~/.codex/auth.json to put
        # it in ApiKey mode (see codex_auth.py for the precedence details).
        # chmod 600 — Codex rejects an auth.json that is group/world-readable.
        api_key = _openai_api_key(spec)
        if api_key:
            handle.workspace().write_text(CODEX_AUTH_PATH, render_codex_auth_json(api_key))
            handle.workspace().chmod(CODEX_AUTH_PATH, 0o600)

        # The TOML rendering — including Codex's strict bearer-token and
        # type validation — lives in agent_on_demand.runtimes.codex_config
        # so it can be mutation-tested without a Sprite. Skip the file
        # write entirely when there's nothing to render; matches the
        # historical behavior of writing the config file only on demand.
        if not mcp_servers:
            return
        body = render_codex_mcp_config(mcp_servers)
        handle.workspace().write_text(CODEX_CONFIG_PATH, body)

    def otel_env(
        self,
        spec: "SessionSpec",
        traceparent: str | None,
        tracestate: str | None,
    ) -> dict[str, str]:
        return {}

    def static_env(self, spec: "SessionSpec") -> list[tuple[str, str]]:
        return []
