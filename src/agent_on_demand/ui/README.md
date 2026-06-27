# UI Package

This package is the built-in Django UI for signup, login, API keys, agent and
environment creation, session control, and resource browsing. It is useful for
operators and dashboard-first users, while the REST API remains the integration
contract for SDKs, CLIs, and external automation.

## Files

- `urls.py` maps `/ui/*` routes.
- `views.py` handles registration, dashboard, API keys, agent and environment
  creation, session actions, and resource detail pages.
- `forms.py` defines registration, API-key, agent, environment, and session
  prompt forms.

Templates and static assets live under `agent_on_demand/templates` and
`agent_on_demand/static`.
