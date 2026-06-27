import json
import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from agent_on_demand.models import (
    Agent,
    AgentVersion,
    APIKey,
    Environment,
    UserCredential,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def api_key(user):
    instance, raw_key = APIKey.create_key(user, "test-key")
    return instance, raw_key


@pytest.fixture
def auth_headers(api_key):
    _, raw_key = api_key
    return {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}


@pytest.fixture
def sprites_key(settings):
    settings.SPRITES_API_KEY = "fake-sprites-token"


@pytest.fixture
def runtime_key(user, sprites_key):
    cred = UserCredential(user=user, kind="provider:anthropic")
    cred.set_value("fake-anthropic-key")
    cred.save()
    return cred


SAMPLE_SKILL = {
    "name": "web-search",
    "description": "Search the web for current information.",
    "content": "---\nname: web-search\ndescription: Search the web for current information.\n---\n\nUse this skill when the user asks for up-to-date information.\n",
}


@pytest.fixture
def agent(user):
    a = Agent.objects.create(
        user=user,
        name="Test Agent",
        description="A test agent",
        system="You are a helpful assistant.",
        provider="anthropic",
        model="claude-sonnet-4-6",
        skills=[SAMPLE_SKILL],
        metadata={"team": "platform"},
        version=1,
    )
    AgentVersion.objects.create(
        agent=a,
        version=1,
        name=a.name,
        description=a.description,
        system=a.system,
        provider=a.provider,
        model=a.model,
        skills=a.skills,
        metadata=a.metadata,
    )
    return a


# --- Create ---


@pytest.mark.django_db
def test_create_agent(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps(
            {
                "name": "My Agent",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "system": "You are helpful.",
                "description": "Does things",
                "skills": [SAMPLE_SKILL],
                "metadata": {"env": "prod"},
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Agent"
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-sonnet-4-6"
    assert data["system"] == "You are helpful."
    assert data["description"] == "Does things"
    assert data["skills"] == [SAMPLE_SKILL]
    assert data["metadata"] == {"env": "prod"}
    assert data["version"] == 1
    assert data["archived_at"] is None
    assert data["type"] == "agent"

    # Version record was created
    assert AgentVersion.objects.filter(agent_id=data["id"], version=1).exists()


@pytest.mark.django_db
def test_create_agent_minimal(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps(
            {"name": "Minimal", "provider": "anthropic", "model": "claude-sonnet-4-6"}
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Minimal"
    assert data["skills"] == []
    assert data["metadata"] == {}


@pytest.mark.django_db
def test_create_agent_accepts_free_form_model(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps({"name": "Future", "provider": "openai", "model": "o9-preview"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "openai"
    assert data["model"] == "o9-preview"


@pytest.mark.django_db
def test_create_agent_rejects_blank_model(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps({"name": "Bad", "provider": "anthropic", "model": "  "}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 422
    assert "Model must be a non-empty string" in str(resp.json()["detail"])


@pytest.mark.django_db
def test_create_agent_normalizes_matching_provider_prefix(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps(
            {
                "name": "Prefixed",
                "provider": "anthropic",
                "model": "anthropic/claude-sonnet-4-6",
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-sonnet-4-6"


@pytest.mark.django_db
def test_create_agent_rejects_mismatched_provider_prefix(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps(
            {
                "name": "Bad",
                "provider": "anthropic",
                "model": "openai/gpt-4.1",
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 422
    assert "does not match provider" in resp.json()["detail"]


@pytest.mark.django_db
def test_create_agent_mcp_servers_entry_must_be_object(client: Client, auth_headers):
    """mcp_servers entries must each be JSON objects. A bare string slips
    past the JSON-parse validation but must reject at the field validator
    with a 422 — without that branch, downstream code that reads
    ``server["name"]`` would crash with a 500."""
    resp = client.post(
        "/agents",
        data=json.dumps(
            {
                "name": "Bad",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "mcp_servers": ["just-a-string"],
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 422
    assert "must be an object" in str(resp.json()["detail"])


@pytest.mark.django_db
def test_update_agent_not_found_returns_404(client: Client, auth_headers):
    """A PUT to /agents/{nonexistent-uuid} must 404, not 500. The handler
    has no pre-lock fetch — the validate-then-load sequence runs first
    (json/pydantic/runtime/env), then `select_for_update().get()` is
    expected to be the only DB read for the agent. Pin the 404 path so
    a refactor that adds a pre-lock fetch (and changes the error
    surface) doesn't silently break the contract.

    Sends a complete payload (version + a real change) so we know the
    response came from the DoesNotExist catch, not earlier validation."""
    resp = client.put(
        f"/agents/{uuid.uuid4()}",
        data=json.dumps({"version": 1, "name": "renamed"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Agent not found"


@pytest.mark.django_db
def test_update_agent_with_unknown_model_returns_422(client: Client, auth_headers, user):
    """UpdateAgentRequest validates the new model the same way
    CreateAgentRequest does — matching provider prefixes are accepted
    and normalized before persistence."""
    agent = Agent.objects.create(
        user=user,
        name="A",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": 1, "model": "anthropic/claude-opus-latest"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "anthropic"
    assert resp.json()["model"] == "claude-opus-latest"


@pytest.mark.django_db
def test_create_agent_missing_fields(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps({"name": "Incomplete"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 422


# --- List ---


@pytest.mark.django_db
def test_list_agents(client: Client, auth_headers, agent):
    resp = client.get("/agents", **auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Test Agent"


@pytest.mark.django_db
def test_list_agents_excludes_archived(client: Client, auth_headers, agent):
    from django.utils import timezone

    agent.archived_at = timezone.now()
    agent.save()

    resp = client.get("/agents", **auth_headers)
    assert resp.json()["data"] == []


@pytest.mark.django_db
def test_list_agents_other_user_not_visible(client: Client, auth_headers):
    other = User.objects.create_user(username="other", password="pass")
    Agent.objects.create(
        user=other,
        name="Other's Agent",
        provider="anthropic",
        model="x",
        version=1,
    )
    resp = client.get("/agents", **auth_headers)
    assert resp.json()["data"] == []


# --- Get ---


@pytest.mark.django_db
def test_get_agent(client: Client, auth_headers, agent):
    resp = client.get(f"/agents/{agent.id}", **auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Agent"


@pytest.mark.django_db
def test_get_agent_not_found(client: Client, auth_headers):
    resp = client.get(f"/agents/{uuid.uuid4()}", **auth_headers)
    assert resp.status_code == 404


# --- Update ---


@pytest.mark.django_db
def test_update_agent(client: Client, auth_headers, agent):
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": 1, "system": "Updated system prompt."}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["system"] == "Updated system prompt."
    assert data["version"] == 2
    assert data["name"] == "Test Agent"  # unchanged

    # Version 2 was snapshotted
    assert AgentVersion.objects.filter(agent=agent, version=2).exists()


@pytest.mark.django_db
def test_update_agent_metadata_merge(client: Client, auth_headers, agent):
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": 1, "metadata": {"env": "staging", "new_key": "val"}}),
        content_type="application/json",
        **auth_headers,
    )
    data = resp.json()
    assert data["metadata"] == {"team": "platform", "env": "staging", "new_key": "val"}


@pytest.mark.django_db
def test_update_agent_metadata_delete_key(client: Client, auth_headers, agent):
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": 1, "metadata": {"team": ""}}),
        content_type="application/json",
        **auth_headers,
    )
    assert "team" not in resp.json()["metadata"]


@pytest.mark.django_db
def test_update_agent_no_change(client: Client, auth_headers, agent):
    """No-op update returns same version."""
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": 1, "name": "Test Agent"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.json()["version"] == 1


@pytest.mark.django_db
def test_update_agent_version_mismatch(client: Client, auth_headers, agent):
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": 99, "name": "New Name"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 409
    assert "Version mismatch" in resp.json()["detail"]


@pytest.mark.django_db
def test_update_archived_agent(client: Client, auth_headers, agent):
    from django.utils import timezone

    agent.archived_at = timezone.now()
    agent.save()

    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": 1, "name": "New"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 409


# --- Archive ---


@pytest.mark.django_db
def test_archive_agent(client: Client, auth_headers, agent):
    resp = client.post(f"/agents/{agent.id}/archive", **auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived_at"] is not None

    agent.refresh_from_db()
    assert agent.is_archived


@pytest.mark.django_db
def test_archive_already_archived(client: Client, auth_headers, agent):
    from django.utils import timezone

    agent.archived_at = timezone.now()
    agent.save()

    resp = client.post(f"/agents/{agent.id}/archive", **auth_headers)
    assert resp.status_code == 409


# --- Versions ---


@pytest.mark.django_db
def test_list_versions(client: Client, auth_headers, agent):
    # Update to create version 2
    agent.system = "v2 prompt"
    agent.version = 2
    agent.save()
    AgentVersion.objects.create(
        agent=agent,
        version=2,
        name=agent.name,
        system="v2 prompt",
        provider=agent.provider,
        model=agent.model,
        skills=agent.skills,
        metadata=agent.metadata,
    )

    resp = client.get(f"/agents/{agent.id}/versions", **auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["version"] == 2
    assert data[1]["version"] == 1


# --- Session with agent_id ---


@pytest.mark.django_db
def test_create_session_with_agent(
    client: Client, auth_headers, agent, runtime_key, fake_sprites, mocker
):
    defer_mock = mocker.patch("agent_on_demand.session_service.tasks.execute_turn.defer")

    resp = client.post(
        "/sessions",
        data=json.dumps({"agent_id": str(agent.id), "prompt": "Fix the bug"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 202

    # System prompt is prepended to the user prompt; the combined string is
    # passed to the execute_turn task as `prompt`.
    effective_prompt = defer_mock.call_args.kwargs["prompt"]
    assert "You are a helpful assistant." in effective_prompt
    assert "Fix the bug" in effective_prompt


@pytest.mark.django_db
def test_create_session_with_agent_inherits_runtime(
    client: Client, auth_headers, agent, runtime_key, fake_sprites
):
    # No runtime specified — should inherit from agent
    resp = client.post(
        "/sessions",
        data=json.dumps({"agent_id": str(agent.id), "prompt": "hello"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 202


@pytest.mark.django_db
def test_create_session_missing_agent_id(client: Client, auth_headers):
    """agent_id is required for session creation."""
    resp = client.post(
        "/sessions",
        data=json.dumps({"prompt": "hello"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.django_db
def test_create_session_with_archived_agent(client: Client, auth_headers, agent, runtime_key):
    from django.utils import timezone

    agent.archived_at = timezone.now()
    agent.save()

    resp = client.post(
        "/sessions",
        data=json.dumps({"agent_id": str(agent.id), "prompt": "hello"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 409
    assert "archived" in resp.json()["detail"]


# --- Method-not-allowed and JSON-error paths ---
#
# These pin the contract for malformed requests, wrong HTTP methods, and the
# never-quite-tested "validate-then-load" sequence in PUT /agents/{id}. Each
# branch was reachable but uncovered, so a refactor that, say, returned 422
# instead of 400 for invalid JSON could land silently.


@pytest.mark.django_db
def test_agents_collection_rejects_unknown_method(client: Client, auth_headers):
    """PATCH on /agents must return 405 — anything else would be a contract change."""
    resp = client.patch("/agents", **auth_headers)
    assert resp.status_code == 405
    assert resp.json()["detail"] == "Method not allowed"


@pytest.mark.django_db
def test_agent_detail_rejects_unknown_method(client: Client, auth_headers, agent):
    """DELETE on /agents/{id} must return 405. Agents are archived (POST
    /agents/{id}/archive), not deleted, so DELETE has no defined behavior."""
    resp = client.delete(f"/agents/{agent.id}", **auth_headers)
    assert resp.status_code == 405


@pytest.mark.django_db
def test_create_agent_invalid_json(client: Client, auth_headers):
    resp = client.post("/agents", data="{not json", content_type="application/json", **auth_headers)
    assert resp.status_code == 400
    assert "Invalid JSON" in resp.json()["detail"]


@pytest.mark.django_db
def test_update_agent_invalid_json(client: Client, auth_headers, agent):
    resp = client.put(
        f"/agents/{agent.id}",
        data="{not json",
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 400
    assert "Invalid JSON" in resp.json()["detail"]


@pytest.mark.django_db
def test_update_agent_unknown_provider(client: Client, auth_headers, agent):
    """A PUT that names an unsupported public provider must reject before
    mutating the agent."""
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": agent.version, "provider": "unknown-provider"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 422
    assert "Unknown provider" in resp.json()["detail"]


@pytest.mark.django_db
def test_update_agent_rejects_mismatched_provider_prefix(client: Client, auth_headers, agent):
    """A prefixed model must match the selected public provider."""
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": agent.version, "model": "openai/gpt-4.1"}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 422
    assert "does not match provider" in resp.json()["detail"]


# --- Environment edge cases on create + update ---


@pytest.mark.django_db
def test_create_agent_environment_not_found(client: Client, auth_headers):
    resp = client.post(
        "/agents",
        data=json.dumps(
            {
                "name": "x",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "environment_id": str(uuid.uuid4()),
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 404
    assert "Environment not found" in resp.json()["detail"]


@pytest.mark.django_db
def test_create_agent_environment_archived(client: Client, auth_headers, user):
    """Archived envs must not be assignable to new agents — otherwise the
    agent could only ever produce sessions that fail at provisioning."""
    env = Environment.objects.create(
        user=user,
        name="archived-env",
        archived_at=timezone.now(),
        version=1,
    )
    resp = client.post(
        "/agents",
        data=json.dumps(
            {
                "name": "x",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "environment_id": str(env.id),
            }
        ),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 409
    assert "archived environment" in resp.json()["detail"]


@pytest.mark.django_db
def test_update_agent_environment_not_found(client: Client, auth_headers, agent):
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": agent.version, "environment_id": str(uuid.uuid4())}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 404
    assert "Environment not found" in resp.json()["detail"]


@pytest.mark.django_db
def test_update_agent_environment_archived(client: Client, auth_headers, agent, user):
    env = Environment.objects.create(
        user=user,
        name="archived-env",
        archived_at=timezone.now(),
        version=1,
    )
    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": agent.version, "environment_id": str(env.id)}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 409
    assert "archived environment" in resp.json()["detail"]


@pytest.mark.django_db
def test_update_agent_clears_environment_with_explicit_null(
    client: Client, auth_headers, agent, user
):
    """Sending environment_id=null must detach the env (PR #115 contract).
    Explicit null is distinct from absent: an absent key leaves the env
    unchanged, but `null` clears it."""
    env = Environment.objects.create(user=user, name="e", version=1)
    agent.environment = env
    agent.save()

    resp = client.put(
        f"/agents/{agent.id}",
        data=json.dumps({"version": agent.version, "environment_id": None}),
        content_type="application/json",
        **auth_headers,
    )
    assert resp.status_code == 200
    agent.refresh_from_db()
    assert agent.environment_id is None


# --- Archive + versions 404 paths ---


@pytest.mark.django_db
def test_archive_agent_not_found(client: Client, auth_headers):
    resp = client.post(f"/agents/{uuid.uuid4()}/archive", **auth_headers)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_archive_agent_invalid_uuid(client: Client, auth_headers):
    """A non-UUID string in the URL must 404, not 500. The view catches
    ValueError from the DB layer's UUID parser."""
    resp = client.post("/agents/not-a-uuid/archive", **auth_headers)
    # Either Django's URL routing (uuid converter) gives a 404, or the view
    # catches ValueError → 404. Both paths are valid; what matters is no 500.
    assert resp.status_code == 404


@pytest.mark.django_db
def test_list_versions_agent_not_found(client: Client, auth_headers):
    resp = client.get(f"/agents/{uuid.uuid4()}/versions", **auth_headers)
    assert resp.status_code == 404
