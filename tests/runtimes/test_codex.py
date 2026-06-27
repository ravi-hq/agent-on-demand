"""CodexRuntime behavior: build_command, write_config (TOML at
/home/sprite/.codex/config.toml), skills_root."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User

from agent_on_demand.models import Environment
from agent_on_demand.runtimes.codex import CODEX_AUTH_PATH, CodexRuntime
from agent_on_demand.session_service.errors import ProvisionError
from agent_on_demand.session_service.specs import McpServerSpec, SessionSpec
from tests.fakes.sprite import RecordingSprite


@pytest.fixture
def user(db):
    return User.objects.create_user(username="codexuser", password="p")


def _spec(
    user,
    *,
    secret_env_vars: dict[str, str] | None = None,
    environment: Environment | None = None,
) -> SessionSpec:
    return SessionSpec(
        name="sprite-x",
        runtime=CodexRuntime(),
        model="gpt-4.1",
        user=user,
        runtime_session_id=None,
        environment=environment,
        repos=[],
        mcp_servers=[],
        skills=[],
        secret_env_vars=secret_env_vars or {},
    )


def test_skills_root():
    assert CodexRuntime().skills_root == "/home/sprite/.codex/skills"


def test_providers():
    assert CodexRuntime().providers == {"openai"}


@pytest.mark.django_db
def test_build_command_run(user):
    argv = CodexRuntime().build_command(_spec(user), "run")
    assert argv == [
        "codex",
        "exec",
        "-m",
        "gpt-4.1",
        "--dangerously-bypass-approvals-and-sandbox",
        "--json",
    ]


@pytest.mark.django_db
def test_build_command_continue(user):
    argv = CodexRuntime().build_command(_spec(user), "continue")
    assert argv == [
        "codex",
        "exec",
        "resume",
        "--last",
        "-m",
        "gpt-4.1",
        "--dangerously-bypass-approvals-and-sandbox",
        "--json",
    ]


@pytest.mark.django_db
def test_write_config_url_server(user):
    sprite = RecordingSprite("s")
    spec = _spec(user)
    CodexRuntime().write_config(
        sprite,
        spec,
        [McpServerSpec(name="github", type="url", url="https://mcp.github.com/mcp")],
    )
    toml = sprite.write_map()["/home/sprite/.codex/config.toml"]
    assert "[mcp_servers.github]" in toml
    assert 'url = "https://mcp.github.com/mcp"' in toml
    assert "required = true" in toml


@pytest.mark.django_db
def test_write_config_bearer_token_env_var(user):
    sprite = RecordingSprite("s")
    spec = _spec(user)
    CodexRuntime().write_config(
        sprite,
        spec,
        [
            McpServerSpec(
                name="api",
                type="url",
                url="https://mcp.example.com/mcp",
                headers={"Authorization": "Bearer ${MY_TOKEN}"},
            )
        ],
    )
    toml = sprite.write_map()["/home/sprite/.codex/config.toml"]
    assert 'bearer_token_env_var = "MY_TOKEN"' in toml


@pytest.mark.django_db
def test_write_config_empty_mcp_servers_writes_no_toml(user):
    sprite = RecordingSprite("s")
    CodexRuntime().write_config(sprite, _spec(user), [])
    assert "/home/sprite/.codex/config.toml" not in sprite.write_map()


# --- auth.json (API-key auth) ------------------------------------------------


@pytest.mark.django_db
def test_write_config_writes_auth_json_from_secret_env_vars(user):
    """The OpenAI key in secret_env_vars must land in ~/.codex/auth.json —
    Codex's exec path won't read a bare OPENAI_API_KEY env var, so without
    this the turn 401s with 'Missing bearer'."""
    sprite = RecordingSprite("s")
    spec = _spec(user, secret_env_vars={"OPENAI_API_KEY": "sk-proj-secret"})
    CodexRuntime().write_config(sprite, spec, [])
    auth = sprite.write_map()[CODEX_AUTH_PATH]
    assert json.loads(auth) == {"OPENAI_API_KEY": "sk-proj-secret"}


@pytest.mark.django_db
def test_write_config_chmods_auth_json_0600(user):
    """Codex refuses an auth.json that is group/world-readable."""
    sprite = RecordingSprite("s")
    spec = _spec(user, secret_env_vars={"OPENAI_API_KEY": "sk-x"})
    CodexRuntime().write_config(sprite, spec, [])
    assert sprite.chmod_map()[CODEX_AUTH_PATH] == 0o600


@pytest.mark.django_db
def test_write_config_auth_json_falls_back_to_environment_env_vars(user):
    """When no session secret carries the key, fall back to the Environment's
    env_vars so an org that pins OPENAI_API_KEY on the Environment still auths."""
    env = Environment.objects.create(
        user=user, name="e", env_vars={"OPENAI_API_KEY": "sk-from-env"}
    )
    sprite = RecordingSprite("s")
    CodexRuntime().write_config(sprite, _spec(user, environment=env), [])
    assert json.loads(sprite.write_map()[CODEX_AUTH_PATH]) == {"OPENAI_API_KEY": "sk-from-env"}


@pytest.mark.django_db
def test_write_config_secret_env_var_overrides_environment(user):
    """secret_env_vars wins over Environment env_vars — mirrors the env-file
    precedence so a per-run key override actually takes effect."""
    env = Environment.objects.create(
        user=user, name="e", env_vars={"OPENAI_API_KEY": "sk-from-env"}
    )
    sprite = RecordingSprite("s")
    spec = _spec(user, secret_env_vars={"OPENAI_API_KEY": "sk-secret"}, environment=env)
    CodexRuntime().write_config(sprite, spec, [])
    assert json.loads(sprite.write_map()[CODEX_AUTH_PATH]) == {"OPENAI_API_KEY": "sk-secret"}


@pytest.mark.django_db
def test_write_config_no_key_writes_no_auth_json(user):
    """With no key anywhere, skip the write — an empty auth.json would put
    Codex in a broken 'ApiKey mode, no key' state instead of a clean fallback."""
    sprite = RecordingSprite("s")
    CodexRuntime().write_config(sprite, _spec(user), [])
    assert CODEX_AUTH_PATH not in sprite.write_map()
    assert CODEX_AUTH_PATH not in sprite.chmod_map()


@pytest.mark.django_db
def test_write_config_writes_both_auth_and_mcp(user):
    """Auth and MCP config coexist — a session with both a key and MCP
    servers must get both files, not one or the other."""
    sprite = RecordingSprite("s")
    spec = _spec(user, secret_env_vars={"OPENAI_API_KEY": "sk-x"})
    CodexRuntime().write_config(
        sprite,
        spec,
        [McpServerSpec(name="github", type="url", url="https://mcp.github.com/mcp")],
    )
    writes = sprite.write_map()
    assert CODEX_AUTH_PATH in writes
    assert "[mcp_servers.github]" in writes["/home/sprite/.codex/config.toml"]


def test_install_is_a_no_op():
    """The Codex CLI is preinstalled in the runtime image, so .install() must
    do nothing — adding work here would silently slow every session start."""
    assert CodexRuntime().install(handle=None) is None


@pytest.mark.django_db
def test_write_config_stdio_server_writes_command_args_env(user):
    """stdio MCP servers are the most common type — confirm command, args
    list, and env block all land in the TOML output."""
    sprite = RecordingSprite("s")
    spec = _spec(user)
    CodexRuntime().write_config(
        sprite,
        spec,
        [
            McpServerSpec(
                name="local",
                type="stdio",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-everything"],
                env={"DEBUG": "1", "API_BASE": "https://x"},
            )
        ],
    )
    toml = sprite.write_map()["/home/sprite/.codex/config.toml"]
    assert "[mcp_servers.local]" in toml
    assert 'command = "npx"' in toml
    assert 'args = ["-y", "@modelcontextprotocol/server-everything"]' in toml
    assert "[mcp_servers.local.env]" in toml
    assert 'DEBUG = "1"' in toml
    assert 'API_BASE = "https://x"' in toml


@pytest.mark.django_db
def test_write_config_stdio_without_args_or_env(user):
    """Optional fields stay out of the output when not provided."""
    sprite = RecordingSprite("s")
    CodexRuntime().write_config(
        sprite,
        _spec(user),
        [McpServerSpec(name="bare", type="stdio", command="run-mcp")],
    )
    toml = sprite.write_map()["/home/sprite/.codex/config.toml"]
    assert 'command = "run-mcp"' in toml
    assert "args = " not in toml
    assert "[mcp_servers.bare.env]" not in toml


@pytest.mark.django_db
def test_write_config_literal_bearer_token_raises(user):
    """Codex's TOML schema only supports `bearer_token_env_var`; a literal
    `Bearer <secret>` value would otherwise be silently dropped or worse,
    written verbatim into the config. Reject loudly at provisioning."""
    sprite = RecordingSprite("s")
    with pytest.raises(ProvisionError) as exc_info:
        CodexRuntime().write_config(
            sprite,
            _spec(user),
            [
                McpServerSpec(
                    name="api",
                    type="url",
                    url="https://mcp.example.com/mcp",
                    headers={"Authorization": "Bearer literal-secret-value"},
                )
            ],
        )
    assert exc_info.value.stage == "write_config"
    assert "literal value" in str(exc_info.value)


@pytest.mark.django_db
def test_write_config_non_authorization_header_raises(user):
    """Codex's MCP config supports exactly one header form
    (`Authorization: Bearer ${ENV}`). Reject anything else loudly so a
    user-supplied custom header doesn't get silently dropped."""
    sprite = RecordingSprite("s")
    with pytest.raises(ProvisionError) as exc_info:
        CodexRuntime().write_config(
            sprite,
            _spec(user),
            [
                McpServerSpec(
                    name="api",
                    type="url",
                    url="https://mcp.example.com/mcp",
                    headers={"X-Custom-Header": "some-value"},
                )
            ],
        )
    assert exc_info.value.stage == "write_config"
    assert "X-Custom-Header" in str(exc_info.value)
