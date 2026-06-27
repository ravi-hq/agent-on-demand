# UI Package

This package is the built-in Django UI for signup, login, API keys, and simple
resource browsing. It is useful for operators and for issuing API tokens, but
the product contract remains the REST API.

## Files

- `urls.py` maps `/ui/*` routes.
- `views.py` handles registration, dashboard, API keys, and resource detail
  pages.
- `forms.py` defines registration and API-key creation forms.

Templates and static assets live under `agent_on_demand/templates` and
`agent_on_demand/static`.
