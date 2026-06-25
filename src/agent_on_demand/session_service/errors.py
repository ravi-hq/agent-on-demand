class SessionServiceError(Exception):
    """Base for all session-service failures."""


class NoBackendCredentialsError(SessionServiceError):
    """The platform backend token (`settings.SPRITES_API_KEY`) is not configured."""


class ProvisionError(SessionServiceError):
    """The backend rejected a provision / prepare / write operation.

    `stage` identifies which setup step failed and is for server-side logging
    only — it must never be sent to API clients.
    """

    def __init__(self, message: str, *, stage: str):
        super().__init__(message)
        self.stage = stage


class SessionHandleNotFound(SessionServiceError):
    """The backing session handle is no longer available on the backend."""
