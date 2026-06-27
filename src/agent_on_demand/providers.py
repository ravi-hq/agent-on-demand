from __future__ import annotations

SUPPORTED_PROVIDERS = ("anthropic", "openai")

PROVIDER_RUNTIME: dict[str, str] = {
    "anthropic": "claude",
    "openai": "codex",
}

RUNTIME_PROVIDER: dict[str, str] = {runtime: provider for provider, runtime in PROVIDER_RUNTIME.items()}

KNOWN_PROVIDER_PREFIXES = frozenset({"anthropic", "openai", "google", "kimi"})


def runtime_for_provider(provider: str) -> str:
    try:
        return PROVIDER_RUNTIME[provider]
    except KeyError as exc:
        raise ValueError(
            f"Unknown provider: {provider}. Must be one of: {list(SUPPORTED_PROVIDERS)}"
        ) from exc


def provider_for_runtime(runtime: str) -> str:
    try:
        return RUNTIME_PROVIDER[runtime]
    except KeyError as exc:
        raise ValueError(f"Runtime {runtime!r} does not map to a public provider") from exc


def normalize_provider_model(provider: str, model: str) -> tuple[str, str]:
    provider = provider.strip()
    model = model.strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider}. Must be one of: {list(SUPPORTED_PROVIDERS)}"
        )
    if not model:
        raise ValueError("Model must be a non-empty string")

    prefix, sep, suffix = model.partition("/")
    if sep and prefix in KNOWN_PROVIDER_PREFIXES:
        if prefix != provider:
            raise ValueError(f"Model provider prefix {prefix!r} does not match provider {provider!r}")
        model = suffix.strip()
        if not model:
            raise ValueError("Model must be a non-empty string")
    return provider, model
