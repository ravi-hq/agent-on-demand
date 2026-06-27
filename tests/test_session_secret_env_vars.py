import pytest
from django.contrib.auth.models import User

from agent_on_demand.models import AgentSession, SessionSecretEnvVars


@pytest.fixture
def user(db):
    return User.objects.create_user(username="secret-user", password="p")


@pytest.fixture
def session(user):
    return AgentSession.objects.create(
        user=user,
        runtime="claude",
        prompt="x",
        status="pending",
    )


@pytest.mark.django_db
def test_session_secret_env_vars_round_trip_encrypted(session):
    row = SessionSecretEnvVars(session=session)
    row.set_env_vars({"ANTHROPIC_API_KEY": "sk-ant-secret", "A_SPACE": "value with space"})
    row.save()

    fetched = SessionSecretEnvVars.objects.get(session=session)

    assert bytes(fetched.encrypted_env_vars) != b"sk-ant-secret"
    assert fetched.get_env_vars() == {
        "A_SPACE": "value with space",
        "ANTHROPIC_API_KEY": "sk-ant-secret",
    }


@pytest.mark.django_db
def test_session_secret_env_vars_cascade_with_session(session):
    row = SessionSecretEnvVars(session=session)
    row.set_env_vars({"OPENAI_API_KEY": "sk-secret"})
    row.save()

    session.delete()

    assert not SessionSecretEnvVars.objects.filter(pk=row.pk).exists()
