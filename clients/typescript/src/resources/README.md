# TypeScript SDK Resources

Resource classes are thin wrappers around AOD REST endpoints.

## Files

- `agents.ts` covers `/agents` create, list, get, update, archive, versions.
- `environments.ts` covers `/environments` create, list, get, update, archive,
  delete, versions.
- `sessions.ts` covers `/sessions` create, list, get, prompt, terminate,
  delete, turns, and stream.
- `index.ts` exports resource classes and parameter types.

## Pattern

Each method builds a request body or query, calls `HttpClient`, and returns
typed objects. Streaming returns a `StreamHandle` so callers can `for await`
events and close the underlying request.
