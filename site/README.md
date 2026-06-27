# Site Package

`site` is the MkDocs documentation site. It turns docs and guides into the
published docs at `ravi-hq.github.io/agent-on-demand`.

## Files

- `mkdocs.yml` configures navigation, theme, and docs source paths.
- `docs/index.md` is the docs landing page.
- `docs/api/*` explains API concepts, auth, errors, runtimes, streaming, and
  reference material.
- `docs/patterns/*` describes product patterns built on AOD.
- `docs/sdks/*` documents Python and TypeScript SDK usage.
- `docs/operators/*` contains deployment/operator guides.
- `overrides/` and `docs/stylesheets/` customize presentation.

Skip `site/site/`; it is generated build output.
