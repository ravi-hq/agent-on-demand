from agent_on_demand.models import AgentSession, SessionTurn
from agent_on_demand.providers import provider_for_runtime


def _session_provider(session: AgentSession) -> str:
    if session.agent_id and session.agent:
        return session.agent.provider
    try:
        return provider_for_runtime(session.runtime)
    except ValueError:
        return session.runtime


def _serialize_resources(session: AgentSession) -> list[dict]:
    """Serialize session resources for API responses (token is never included)."""
    return [
        {
            "type": sr.resource_type,
            "url": sr.url,
            "mount_path": sr.mount_path,
        }
        for sr in session.resources.all()
    ]


def _serialize_session(session: AgentSession) -> dict:
    latest = session.turns.order_by("-turn_number").first()
    return {
        "id": str(session.id),
        "agent_id": str(session.agent_id) if session.agent_id else None,
        "environment_id": str(session.environment_id) if session.environment_id else None,
        "provider": _session_provider(session),
        "status": session.status,
        "exit_code": session.exit_code,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "resources": _serialize_resources(session),
        "turn_count": session.turns.count(),
        "current_turn": latest.turn_number if latest else None,
    }


def _serialize_turn(turn: SessionTurn) -> dict:
    return {
        "turn_number": turn.turn_number,
        "prompt": turn.prompt,
        "status": turn.status,
        "exit_code": turn.exit_code,
        "created_at": turn.created_at.isoformat(),
        "started_at": turn.started_at.isoformat() if turn.started_at else None,
        "ended_at": turn.ended_at.isoformat() if turn.ended_at else None,
    }
