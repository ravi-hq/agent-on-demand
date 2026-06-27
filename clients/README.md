# Clients Package

`clients` contains the official SDKs. They expose the same AOD REST concepts
as language-native clients.

```mermaid
flowchart TD
  OpenAPI["docs/openapi.yaml"] --> Python["python/aod-sdk"]
  OpenAPI --> TypeScript["typescript/@ravi-hq/aod-sdk"]
  Python --> API["AOD HTTP API"]
  TypeScript --> API
```

## Index

- [`python/`](python/README.md) is the published `aod-sdk` package.
- [`typescript/`](typescript/README.md) is the published
  `@ravi-hq/aod-sdk` package.

Skip `.venv`, `dist`, caches, and generated declaration output.
