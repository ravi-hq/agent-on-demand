# Session Views Package

This subpackage owns the most important API flow: creating, continuing,
streaming, terminating, and deleting agent sessions.

```mermaid
sequenceDiagram
  participant Client
  participant Create as create.py
  participant DB
  participant Queue as Procrastinate
  participant Lifecycle as lifecycle.py
  participant Stream as stream.py
  Client->>Create: POST /sessions
  Create->>DB: validate agent/env/quota, create rows
  Create->>Queue: provision_session_task.defer
  Create-->>Client: 202
  Client->>Stream: GET /sessions/{id}/stream
  Stream->>DB: replay AgentSessionLog rows
  Client->>Lifecycle: POST /sessions/{id}/prompt
  Lifecycle->>Queue: execute_turn.defer
```

## Files

- `schemas.py` defines `RunRequest`, `PromptRequest`, and GitHub resource
  request models.
- `serializers.py` maps sessions, resources, and turns to API JSON.
- `create.py` validates session creation, quota, runtime/model compatibility,
  credentials, and resource rows.
- `lifecycle.py` handles detail, follow-up prompts, turns, terminate, and
  delete.
- `stream.py` exposes async SSE replay with `Last-Event-ID`/`since` support.

## Important Boundary

`create.py` does not provision or run the agent inline. It writes rows, enqueues
`provision_session_task`, and returns quickly. Worker code owns Sprite work.
