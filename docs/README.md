# Docs Package

`docs` contains source-of-truth API artifacts used by tests, validation, and
published documentation.

## Files

- `openapi.yaml` is the hand-maintained OpenAPI contract.
- `API.md` is a human-readable API reference.
- `request_schemas.json` snapshots pydantic request schemas.
- `runbook.md` is an operator runbook.

## Related Scripts

- `scripts/validate_openapi.py` compares Django routes to the OpenAPI paths.
- `scripts/check_request_schemas.py` detects request schema drift.
- `scripts/check_sdk_parity.py` checks SDK endpoint coverage.
