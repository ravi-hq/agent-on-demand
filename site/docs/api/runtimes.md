# Runtimes

A **runtime** is the CLI that Agent on Demand invokes inside the Sprite to drive the model.
It is an internal session execution detail. API clients choose a public `provider` plus
a free-form `model` string; AOD maps the provider to a runtime when the session starts.

Public providers currently map as follows:

| Provider | Internal runtime | API key env var |
| -------- | ---------------- | --------------- |
| `anthropic` | Claude Code (`claude`) | `ANTHROPIC_API_KEY` |
| `openai` | OpenAI Codex CLI (`codex`) | `OPENAI_API_KEY` |

Model strings are free-form and provider-specific. Matching legacy prefixes are accepted:
`provider=anthropic` with `model=anthropic/claude-sonnet` is normalized to
`model=claude-sonnet`. Mismatched prefixes such as `provider=anthropic`,
`model=openai/o3` return 422.

## Setting provider and model on an agent

Pass `provider` and `model` when creating the agent:

```bash
curl -X POST https://aod.ravi.id/agents \
  -H "Authorization: Bearer $AOD_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hello",
    "provider": "anthropic",
    "model": "claude-sonnet"
  }'
```

`provider` must be one of the supported public providers. `model` is not catalog-validated.

## Supplying API keys

Each provider reads its API key from a specific env var at session start. AOD does not
store reusable per-user provider credentials. Trusted callers supply BYOK values as
session-scoped `secret_env_vars` on `POST /sessions`; AOD encrypts those values at rest,
writes them into the Sprite's `/tmp/aod-env`, and never returns them in API responses.

`env_vars` on an environment are also sourced into the session. `secret_env_vars` land
last, so explicit per-run BYOK values override reusable environment configuration.
Environment env var values are never echoed back in API responses. See
[Core Concepts → Environments](concepts.md#environments) for the full shape.

If neither `secret_env_vars` nor the attached environment supplies the expected env var,
the runtime CLI fails on startup and the session transitions to `failed`.

## Per-runtime notes

### `claude`

Uses the Claude Code CLI in `--print` + `stream-json` mode. AoD pre-generates a UUID at
session create and passes it as `--session-id` on the first turn, then `--resume <uuid>`
on every subsequent turn — more reliable than `--continue` in non-interactive mode.

#### OAuth auth variant

The `claude` runtime also supports Claude Pro/Max OAuth tokens. Supply
`CLAUDE_CODE_OAUTH_TOKEN` in session `secret_env_vars` instead of
`ANTHROPIC_API_KEY`. Everything else — models, resume semantics, output format —
is identical.

### `codex`

Uses `codex exec` with `--dangerously-bypass-approvals-and-sandbox --json`. The prompt
is piped in on stdin for the first turn; subsequent turns use `codex exec resume --last`
to continue in-place.

### `gemini`

Uses the Gemini CLI with `--output-format stream-json`. Resume is handled via `--resume`.

### `opencode`

Uses [sst/opencode](https://opencode.ai) — a multi-provider CLI that fronts Anthropic,
OpenAI, and Google models through a single binary.

opencode is **not pre-installed** on the Sprite base image. AoD runs
`npm install -g opencode-ai` during the `provision_setup` stage, which runs before any
network policy is applied. `registry.npmjs.org` does not need to be in `allowed_hosts`.
First-session provisioning takes 10–30 s longer than the pre-baked runtimes as a result.

## Tools

All runtimes run with their vendor CLI's **full default tool set** — `bash`, `read`,
`write`, `edit`, `glob`, `grep`, `web_fetch`, `web_search`, and so on. There is no
per-agent allowlist for built-in tools, and no way to disable a specific built-in.
Any MCP servers you configure on the agent are exposed to the runtime on top of the
default tools.

This is intentional: Sprites are disposable sandboxes, so the tool surface is bounded
by the Sprite itself rather than by a runtime-level policy.

## Streaming output shape

Every session stream emits a `start` event with `provider` set to the public provider, followed by
the runtime's native streaming format wrapped in `output` events, then an `exit` event
with the process exit code. See [Streaming](streaming.md) for the full event envelope.
