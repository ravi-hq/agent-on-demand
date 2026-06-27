import pytest

from agent_on_demand.providers import normalize_provider_model, provider_for_runtime, runtime_for_provider


def test_runtime_for_provider_maps_public_provider_to_internal_runtime():
    assert runtime_for_provider("anthropic") == "claude"
    assert runtime_for_provider("openai") == "codex"


def test_provider_for_runtime_maps_internal_runtime_to_public_provider():
    assert provider_for_runtime("claude") == "anthropic"
    assert provider_for_runtime("codex") == "openai"


def test_normalize_provider_model_strips_matching_provider_prefix():
    assert normalize_provider_model("anthropic", "anthropic/claude-sonnet-4-6") == (
        "anthropic",
        "claude-sonnet-4-6",
    )


def test_normalize_provider_model_accepts_free_form_unprefixed_model():
    assert normalize_provider_model("openai", "future-model-123") == ("openai", "future-model-123")


def test_normalize_provider_model_rejects_mismatched_known_prefix():
    with pytest.raises(ValueError, match="does not match provider"):
        normalize_provider_model("anthropic", "openai/o3")


def test_normalize_provider_model_rejects_blank_model():
    with pytest.raises(ValueError, match="non-empty"):
        normalize_provider_model("anthropic", "  ")
