# Python SDK Pretty Printers

Pretty printers are optional display helpers for runtime-specific stdout. They
are intentionally outside the core SDK contract because runtime CLI output can
change independently of the AOD API.

## Files

- `__init__.py` defines the formatter protocol, a generic fallback formatter,
  and `formatter_for`.
- `claude.py` parses Claude CLI `stream-json` output into readable lines.

Use these helpers in CLIs or dashboards that want a better terminal-like
display while still preserving raw stream events.
