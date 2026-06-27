# Specs Package

Specs convert mutable ORM rows into immutable dataclasses used by provisioning
and runtime execution.

## Files

- `types.py` defines `RepoSpec`, `McpServerSpec`, `SkillSpec`, and
  `SessionSpec`.
- `factory.py` builds a `SessionSpec` from an `AgentSession`, pulling in the
  agent, environment, resources, credentials, MCP servers, skills, networking,
  and runtime metadata.

## Why This Exists

The worker needs a stable, testable contract that is not tied to Django model
methods. Build the spec once near the task boundary, then pass the spec through
provisioning and runtime adapters.
