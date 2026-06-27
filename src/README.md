# Agent on Demand Source

`src` contains the Django project and application code for AOD. The service is
an execution plane: the web process creates durable rows and enqueues work; the
worker provisions a Sprite, runs the runtime CLI, persists logs, and updates
session state.

```mermaid
sequenceDiagram
  participant Client
  participant Web as Django web
  participant DB as Postgres
  participant Worker as Procrastinate worker
  participant Sprite
  Client->>Web: POST /sessions
  Web->>DB: create AgentSession, SessionTurn, resources
  Web->>Worker: provision_session_task.defer
  Web-->>Client: 202 + stream_url
  Worker->>Sprite: create + provision
  Worker->>DB: stage/output logs
  Worker->>Sprite: runtime command
  Worker->>DB: final status
  Client->>Web: GET /sessions/{id}/stream
  Web->>DB: replay AgentSessionLog rows as SSE
```

## Index

- [`config/`](config/README.md) is the Django project wrapper.
- [`agent_on_demand/`](agent_on_demand/README.md) is the API, models,
  validation, runtime, and worker package.

Skip migrations and static/template assets on a first read. The architectural
chapters are models, views, runtimes, session service, validation, and stream.
