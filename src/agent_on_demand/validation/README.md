# Validation Package

This package contains request-shape and compatibility validation that should be
shared across API views and tests.

## Files

- `environment_validation.py` validates packages, env vars, and networking.
- `github_resource_validation.py` validates repository URLs, mount paths, and
  resource count/deduplication.
- `mcp_server_validation.py` validates MCP server shape and limits.
- `skill_validation.py` validates inline and GitHub skill references.
- `metadata_merge.py` merges metadata patches.

## Rule Of Thumb

Put validation here when it is a reusable business rule. Keep one-off request
parsing in the relevant view schema.
