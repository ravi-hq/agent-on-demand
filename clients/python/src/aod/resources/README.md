# Python SDK Resources

Resource modules implement the language-native API surface over HTTP paths.
Each resource has sync and async classes with matching method names.

## Files

- `agents.py` covers `/agents` create, list, get, update, archive, versions.
- `environments.py` covers `/environments` create, list, get, update, archive,
  delete, versions.
- `sessions.py` covers `/sessions` create, list, get, prompt, terminate,
  delete, turns, and stream.
- `__init__.py` exports the resource classes.

## Pattern

Normalize user input into request JSON, call `_http.check_response`, and return
pydantic models. Keep server behavior in the server; SDK resources should stay
predictable wrappers.
