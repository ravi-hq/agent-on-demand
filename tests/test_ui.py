import pytest
from django.contrib.auth.models import User
from django.test import Client

from agent_on_demand.models import (
    Agent,
    AgentVersion,
    AgentSession,
    APIKey,
    Environment,
    EnvironmentVersion,
    SessionTurn,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="alicepass123!")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="bob", password="bobpass123!")


@pytest.fixture
def logged_in_client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def sprites_key(settings):
    settings.SPRITES_API_KEY = "fake-sprites-token"


@pytest.fixture
def runtime_key(user, sprites_key):
    return {"ANTHROPIC_API_KEY": "fake-anthropic-key"}


@pytest.mark.django_db
def test_dashboard_requires_login(client: Client):
    resp = client.get("/ui/")
    assert resp.status_code == 302
    assert "/ui/login" in resp.url


@pytest.mark.django_db
def test_landing_is_public(client: Client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Agent on Demand" in body
    assert "/ui/register" in body
    assert "ravi-hq.github.io/agent-on-demand" in body


@pytest.mark.django_db
def test_landing_shows_dashboard_cta_when_logged_in(logged_in_client: Client):
    resp = logged_in_client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Open dashboard" in body
    assert "Create an account" not in body


@pytest.mark.django_db
def test_register_provisions_api_key(client: Client):
    resp = client.post(
        "/ui/register",
        data={
            "username": "charlie",
            "password1": "supersecret123!",
            "password2": "supersecret123!",
        },
    )
    assert resp.status_code == 302
    assert resp.url == "/ui/welcome"

    charlie = User.objects.get(username="charlie")
    assert APIKey.objects.filter(user=charlie, is_active=True).count() == 1


@pytest.mark.django_db
def test_register_mismatched_passwords_rejected(client: Client):
    resp = client.post(
        "/ui/register",
        data={
            "username": "dave",
            "password1": "a",
            "password2": "b",
        },
    )
    assert resp.status_code == 200
    assert not User.objects.filter(username="dave").exists()


@pytest.mark.django_db
def test_welcome_shows_raw_key_once(client: Client):
    resp = client.post(
        "/ui/register",
        data={
            "username": "frank",
            "password1": "supersecret123!",
            "password2": "supersecret123!",
        },
    )
    assert resp.status_code == 302

    resp = client.get("/ui/welcome")
    assert resp.status_code == 200
    assert b"aod_" in resp.content
    assert b"curl" in resp.content
    assert b"/ui/" in resp.content  # dashboard link

    resp = client.get("/ui/welcome")
    assert resp.status_code == 302
    assert resp.url == "/ui/"


@pytest.mark.django_db
def test_welcome_requires_login(client: Client):
    resp = client.get("/ui/welcome")
    assert resp.status_code == 302
    assert "/ui/login" in resp.url


@pytest.mark.django_db
def test_register_redirects_if_authenticated(logged_in_client):
    resp = logged_in_client.get("/ui/register")
    assert resp.status_code == 302
    assert resp.url == "/ui/"


@pytest.mark.django_db
def test_login_logout_flow(client: Client, user):
    resp = client.post("/ui/login", data={"username": "alice", "password": "alicepass123!"})
    assert resp.status_code == 302
    resp = client.get("/ui/")
    assert resp.status_code == 200
    assert b"Dashboard" in resp.content

    resp = client.post("/ui/logout")
    assert resp.status_code == 302
    resp = client.get("/ui/")
    assert resp.status_code == 302


@pytest.mark.django_db
def test_dashboard_renders_for_logged_in_user(logged_in_client):
    resp = logged_in_client.get("/ui/")
    assert resp.status_code == 200
    assert b"Dashboard" in resp.content
    assert b"read-only" not in resp.content
    assert b"Use Nebula or the API" not in resp.content
    assert b"Create agents" in resp.content


@pytest.mark.django_db
def test_api_key_create_shows_raw_once(logged_in_client, user):
    resp = logged_in_client.post(
        "/ui/api-keys", data={"name": "cli", "expires_at": ""}, follow=False
    )
    assert resp.status_code == 200
    assert b"Copy this key now" in resp.content
    assert APIKey.objects.filter(user=user, is_active=True).count() == 1


@pytest.mark.django_db
def test_api_key_revoke(logged_in_client, user):
    key, _raw = APIKey.create_key(user, "to-revoke")
    resp = logged_in_client.post(f"/ui/api-keys/{key.id}/revoke")
    assert resp.status_code == 302
    key.refresh_from_db()
    assert key.is_active is False


@pytest.mark.django_db
def test_api_key_revoke_scoped_to_owner(logged_in_client, other_user):
    key, _raw = APIKey.create_key(other_user, "not-mine")
    resp = logged_in_client.post(f"/ui/api-keys/{key.id}/revoke")
    assert resp.status_code == 404
    key.refresh_from_db()
    assert key.is_active is True


@pytest.mark.django_db
def test_agents_list_only_shows_owned(logged_in_client, user, other_user):
    mine = Agent.objects.create(
        user=user,
        name="mine",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    theirs = Agent.objects.create(
        user=other_user,
        name="theirs",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    resp = logged_in_client.get("/ui/agents")
    assert resp.status_code == 200
    assert mine.name.encode() in resp.content
    assert theirs.name.encode() not in resp.content


@pytest.mark.django_db
def test_agents_list_exposes_new_agent_link_not_create_form(logged_in_client):
    resp = logged_in_client.get("/ui/agents")
    assert resp.status_code == 200
    assert b"New agent" in resp.content
    assert b"/ui/agents/new" in resp.content
    assert b"Create one via the API" not in resp.content
    assert b'name="name"' not in resp.content


@pytest.mark.django_db
def test_agent_new_renders_create_agent_form(logged_in_client):
    resp = logged_in_client.get("/ui/agents/new")
    assert resp.status_code == 200
    assert b"Create agent" in resp.content
    assert b'name="name"' in resp.content
    assert b'name="provider"' in resp.content
    assert b'name="model"' in resp.content
    assert b'placeholder="claude-sonnet or claude-opus"' in resp.content
    assert b'id="model-help"' not in resp.content
    assert b'name="runtime"' not in resp.content


@pytest.mark.django_db
def test_create_agent_from_dashboard(logged_in_client, user):
    resp = logged_in_client.post(
        "/ui/agents/new",
        data={
            "name": "Dashboard Agent",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "description": "Handles dashboard work",
            "system": "You are precise.",
            "environment_id": "",
        },
    )
    agent = Agent.objects.get(user=user, name="Dashboard Agent")
    assert resp.status_code == 302
    assert resp.url == f"/ui/agents/{agent.id}"
    assert agent.provider == "anthropic"
    assert agent.model == "claude-sonnet-4-6"
    assert agent.description == "Handles dashboard work"
    assert agent.system == "You are precise."
    assert agent.version == 1
    assert AgentVersion.objects.filter(agent=agent, version=1).exists()


@pytest.mark.django_db
def test_create_agent_from_dashboard_rejects_other_users_environment(logged_in_client, other_user):
    theirs = Environment.objects.create(user=other_user, name="not-mine", version=1)
    resp = logged_in_client.post(
        "/ui/agents/new",
        data={
            "name": "Bad Agent",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "environment_id": str(theirs.id),
        },
    )
    assert resp.status_code == 200
    assert b"Environment not found" in resp.content
    assert not Agent.objects.filter(name="Bad Agent").exists()


@pytest.mark.django_db
def test_agents_list_rejects_create_post(logged_in_client):
    resp = logged_in_client.post("/ui/agents", data={"name": "wrong-place"})
    assert resp.status_code == 405


@pytest.mark.django_db
def test_agent_new_rejects_unsupported_methods(logged_in_client):
    resp = logged_in_client.put("/ui/agents/new", data={"name": "wrong-method"})
    assert resp.status_code == 405


@pytest.mark.django_db
def test_agent_detail_404_for_other_user(logged_in_client, other_user):
    theirs = Agent.objects.create(
        user=other_user,
        name="theirs",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    resp = logged_in_client.get(f"/ui/agents/{theirs.id}")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_environment_list_and_detail(logged_in_client, user):
    env = Environment.objects.create(user=user, name="myenv", version=1)
    resp = logged_in_client.get("/ui/environments")
    assert resp.status_code == 200
    assert b"myenv" in resp.content

    resp = logged_in_client.get(f"/ui/environments/{env.id}")
    assert resp.status_code == 200
    assert b"myenv" in resp.content


@pytest.mark.django_db
def test_environments_list_exposes_new_environment_link(logged_in_client):
    resp = logged_in_client.get("/ui/environments")
    assert resp.status_code == 200
    assert b"New environment" in resp.content
    assert b"/ui/environments/new" in resp.content
    assert b'name="name"' not in resp.content


@pytest.mark.django_db
def test_environment_new_renders_create_environment_form(logged_in_client):
    resp = logged_in_client.get("/ui/environments/new")
    assert resp.status_code == 200
    assert b"Create environment" in resp.content
    assert b'name="name"' in resp.content
    assert b'name="packages_json"' in resp.content
    assert b'name="env_vars_json"' in resp.content


@pytest.mark.django_db
def test_create_environment_from_dashboard(logged_in_client, user):
    resp = logged_in_client.post(
        "/ui/environments/new",
        data={
            "name": "Dashboard Env",
            "packages_json": '{"pip": ["pytest"]}',
            "env_vars_json": '{"AOD_MODE": "test"}',
            "setup_script": "echo ready",
            "networking_type": "limited",
            "allowed_hosts": "api.example.com\nassets.example.com",
        },
    )
    env = Environment.objects.get(user=user, name="Dashboard Env")
    assert resp.status_code == 302
    assert resp.url == f"/ui/environments/{env.id}"
    assert env.packages == {"pip": ["pytest"]}
    assert env.env_vars == {"AOD_MODE": "test"}
    assert env.setup_script == "echo ready"
    assert env.networking_type == "limited"
    assert env.networking_config == {"allowed_hosts": ["api.example.com", "assets.example.com"]}
    assert EnvironmentVersion.objects.filter(environment=env, version=1).exists()


@pytest.mark.django_db
def test_create_environment_from_dashboard_rejects_invalid_json(logged_in_client):
    resp = logged_in_client.post(
        "/ui/environments/new",
        data={
            "name": "Bad Env",
            "packages_json": '{"pip": [}',
            "env_vars_json": "{}",
            "networking_type": "unrestricted",
        },
    )
    assert resp.status_code == 200
    assert b"Enter valid JSON" in resp.content
    assert not Environment.objects.filter(name="Bad Env").exists()


@pytest.mark.django_db
def test_environments_list_rejects_create_post(logged_in_client):
    resp = logged_in_client.post("/ui/environments", data={"name": "wrong-place"})
    assert resp.status_code == 405


@pytest.mark.django_db
def test_environment_new_rejects_unsupported_methods(logged_in_client):
    resp = logged_in_client.put("/ui/environments/new", data={"name": "wrong-method"})
    assert resp.status_code == 405


@pytest.mark.django_db
def test_environment_empty_state_does_not_claim_dashboard_is_api_only(logged_in_client):
    resp = logged_in_client.get("/ui/environments")
    assert resp.status_code == 200
    assert b"Create one via the API" not in resp.content
    assert b"Use New environment" in resp.content


@pytest.mark.django_db
def test_sessions_list_and_detail(logged_in_client, user):
    session = AgentSession.objects.create(
        user=user, runtime="claude", prompt="hello world", status="completed", exit_code=0
    )
    resp = logged_in_client.get("/ui/sessions")
    assert resp.status_code == 200
    assert str(session.id)[:8].encode() in resp.content

    resp = logged_in_client.get(f"/ui/sessions/{session.id}")
    assert resp.status_code == 200
    assert b"hello world" in resp.content


@pytest.mark.django_db
def test_sessions_empty_state_points_to_agent_page(logged_in_client):
    resp = logged_in_client.get("/ui/sessions")
    assert resp.status_code == 200
    assert b"Create one via the API" not in resp.content
    assert b"Start one from an agent page" in resp.content


@pytest.mark.django_db
def test_session_detail_404_for_other_user(logged_in_client, other_user):
    theirs = AgentSession.objects.create(
        user=other_user, runtime="claude", prompt="x", status="completed"
    )
    resp = logged_in_client.get(f"/ui/sessions/{theirs.id}")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_ui_does_not_expose_env_var_values(logged_in_client, user):
    env = Environment.objects.create(
        user=user,
        name="secrets",
        env_vars={"DATABASE_URL": "postgres://super-secret"},
        version=1,
    )
    resp = logged_in_client.get(f"/ui/environments/{env.id}")
    assert resp.status_code == 200
    assert b"DATABASE_URL" in resp.content
    assert b"super-secret" not in resp.content


# --- GET-form-render coverage ---
#
# Existing tests POST submissions and assert resulting state. The plain
# GET-renders that show empty forms had no coverage — a refactor that
# returned 500 (e.g. a template syntax error in the empty-state branch)
# would slip past CI.


@pytest.mark.django_db
def test_register_get_renders_form(client: Client):
    resp = client.get("/ui/register")
    assert resp.status_code == 200
    # The form template references the field id_username produced by Django.
    assert b"id_username" in resp.content


@pytest.mark.django_db
def test_api_keys_get_renders_form(logged_in_client):
    resp = logged_in_client.get("/ui/api-keys")
    assert resp.status_code == 200
    assert b"<form" in resp.content


@pytest.mark.django_db
def test_agent_detail_renders_for_owner(logged_in_client, user):
    """`test_agent_detail_404_for_other_user` pins the negative case;
    this pins the positive render so a template-rendering regression
    can't slip past."""
    agent = Agent.objects.create(
        user=user,
        name="Owned-Agent",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    resp = logged_in_client.get(f"/ui/agents/{agent.id}")
    assert resp.status_code == 200
    assert b"Owned-Agent" in resp.content


@pytest.mark.django_db
def test_agent_detail_exposes_dashboard_actions(logged_in_client, user):
    agent = Agent.objects.create(
        user=user,
        name="Action Agent",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    resp = logged_in_client.get(f"/ui/agents/{agent.id}")
    assert resp.status_code == 200
    assert b"Start session" in resp.content
    assert f"/ui/agents/{agent.id}/sessions".encode() in resp.content
    assert f"/ui/agents/{agent.id}/archive".encode() in resp.content


@pytest.mark.django_db
def test_start_session_from_agent_dashboard(logged_in_client, user, runtime_key, fake_sprites):
    agent = Agent.objects.create(
        user=user,
        name="Runner",
        provider="anthropic",
        model="claude-sonnet-4-6",
        system="System prep",
        version=1,
    )
    resp = logged_in_client.post(
        f"/ui/agents/{agent.id}/sessions",
        data={"prompt": "ship it", "timeout": "120"},
    )
    assert resp.status_code == 302

    session = AgentSession.objects.get(user=user, agent=agent)
    assert resp.url == f"/ui/sessions/{session.id}"
    assert session.prompt == "ship it"
    assert session.status in {"pending", "running", "completed"}
    assert SessionTurn.objects.filter(session=session, turn_number=1, prompt="ship it").exists()


@pytest.mark.django_db
def test_start_session_from_agent_dashboard_scoped_to_owner(logged_in_client, other_user):
    theirs = Agent.objects.create(
        user=other_user,
        name="Theirs",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    resp = logged_in_client.post(
        f"/ui/agents/{theirs.id}/sessions",
        data={"prompt": "nope", "timeout": "120"},
    )
    assert resp.status_code == 404
    assert not AgentSession.objects.filter(agent=theirs).exists()


@pytest.mark.django_db
def test_archive_agent_from_dashboard(logged_in_client, user):
    agent = Agent.objects.create(
        user=user,
        name="Archive Me",
        provider="anthropic",
        model="claude-sonnet-4-6",
        version=1,
    )
    resp = logged_in_client.post(f"/ui/agents/{agent.id}/archive")
    assert resp.status_code == 302
    assert resp.url == f"/ui/agents/{agent.id}"

    agent.refresh_from_db()
    assert agent.is_archived


@pytest.mark.django_db
def test_archive_environment_from_dashboard(logged_in_client, user):
    env = Environment.objects.create(user=user, name="Archive Env", version=1)
    resp = logged_in_client.post(f"/ui/environments/{env.id}/archive")
    assert resp.status_code == 302
    assert resp.url == f"/ui/environments/{env.id}"

    env.refresh_from_db()
    assert env.is_archived


@pytest.mark.django_db
def test_session_detail_exposes_session_actions(logged_in_client, user):
    session = AgentSession.objects.create(
        user=user,
        runtime="claude",
        prompt="hello",
        status="completed",
        backend_handle="sprite-one",
    )
    resp = logged_in_client.get(f"/ui/sessions/{session.id}")
    assert resp.status_code == 200
    assert b"Send follow-up" in resp.content
    assert f"/ui/sessions/{session.id}/prompt".encode() in resp.content
    assert f"/ui/sessions/{session.id}/terminate".encode() in resp.content


@pytest.mark.django_db
def test_send_followup_from_session_dashboard(logged_in_client, user, mocker):
    session = AgentSession.objects.create(
        user=user,
        runtime="claude",
        prompt="first",
        status="completed",
        backend_handle="sprite-one",
    )
    SessionTurn.objects.create(session=session, turn_number=1, prompt="first", status="completed")
    resume = mocker.patch("agent_on_demand.session_service.resume_session")
    enqueue = mocker.patch("agent_on_demand.session_service.tasks.execute_turn.defer")

    resp = logged_in_client.post(
        f"/ui/sessions/{session.id}/prompt",
        data={"prompt": "next", "timeout": "300"},
    )
    assert resp.status_code == 302
    assert resp.url == f"/ui/sessions/{session.id}"

    session.refresh_from_db()
    assert session.status == "pending"
    assert session.prompt == "next"
    assert session.exit_code is None
    assert SessionTurn.objects.filter(session=session, turn_number=2, prompt="next").exists()
    resume.assert_called_once_with("sprite-one")
    enqueue.assert_called_once()


@pytest.mark.django_db
def test_send_followup_from_session_dashboard_rejects_running(logged_in_client, user, mocker):
    session = AgentSession.objects.create(
        user=user,
        runtime="claude",
        prompt="first",
        status="running",
        backend_handle="sprite-one",
    )
    resume = mocker.patch("agent_on_demand.session_service.resume_session")

    resp = logged_in_client.post(
        f"/ui/sessions/{session.id}/prompt",
        data={"prompt": "next", "timeout": "300"},
    )
    assert resp.status_code == 302
    assert resp.url == f"/ui/sessions/{session.id}"

    session.refresh_from_db()
    assert session.status == "running"
    assert not SessionTurn.objects.filter(session=session, prompt="next").exists()
    resume.assert_not_called()


@pytest.mark.django_db
def test_terminate_session_from_dashboard(logged_in_client, user, mocker):
    session = AgentSession.objects.create(
        user=user,
        runtime="claude",
        prompt="stop",
        status="running",
        backend_handle="sprite-one",
    )
    destroy = mocker.patch("agent_on_demand.session_service.destroy_session_task.defer")

    resp = logged_in_client.post(f"/ui/sessions/{session.id}/terminate")
    assert resp.status_code == 302
    assert resp.url == f"/ui/sessions/{session.id}"

    session.refresh_from_db()
    assert session.status == "terminated"
    assert session.backend_handle == ""
    destroy.assert_called_once()
