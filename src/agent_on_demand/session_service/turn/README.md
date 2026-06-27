# Turn Helpers Package

This package holds small helpers around individual turns.

## Files

- `enqueue.py` creates a `SessionTurn` and defers `execute_turn`.
- `argv.py` builds shell argv and env-source shims for runtime invocation.
- `outcome.py` maps process results and termination state to final statuses.

The large state machine lives one level up in `turn_executor.py`.
