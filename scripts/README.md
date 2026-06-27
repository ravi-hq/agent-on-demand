# Scripts Package

Scripts are maintenance and CI helpers. They are not runtime code, but they
protect the server, docs, and SDK contracts.

## Files

- `validate_openapi.py` checks Django routes against `docs/openapi.yaml`.
- `check_request_schemas.py` snapshots pydantic request schemas.
- `check_sdk_parity.py` compares SDK endpoints to OpenAPI paths.
- `scope_e2e.py` decides which e2e tests are relevant for a change set.
- `check_mutmut.py` and `mutmut_report.py` run and report mutation testing.
- `auto_revert.py` watches failed deploys and opens revert PRs.

## When To Read

Read this chapter when CI fails on docs/schema parity, SDK coverage, mutation
testing, or deploy auto-revert behavior.
