import logging

from django.conf import settings

from .backends import BackendClient, BackendError, get_backend
from .errors import NoBackendCredentialsError

logger = logging.getLogger(__name__)


def get_client(backend: str = "sprites") -> BackendClient | None:
    """Build a backend client from the platform's configured token.

    The backend token (`settings.SPRITES_API_KEY`) is a single platform-owned
    secret shared by every session — there is no per-user token. Returns None
    when it is unset, which is a deploy misconfiguration that callers surface
    as a 503 rather than a per-user error.

    Raises `NoBackendCredentialsError` if `backend` is not a registered
    backend — that's a programmer error, not a missing-token gap.
    """
    try:
        impl = get_backend(backend)
    except KeyError as e:
        raise NoBackendCredentialsError(str(e)) from e
    token = settings.SPRITES_API_KEY
    if not token:
        return None
    return impl.create_client(token)


def require_client(backend: str = "sprites") -> BackendClient:
    client = get_client(backend)
    if client is None:
        raise NoBackendCredentialsError("Session backend token is not configured")
    return client


def best_effort_delete(client: BackendClient, name: str) -> None:
    try:
        client.destroy(name)
    except BackendError:
        logger.warning("Failed to cleanup session %s", name, exc_info=True)
