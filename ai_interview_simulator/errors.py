class AuthError(Exception):
    """User is not logged in (HTTP 401)."""

class Forbidden(Exception):
    """User is logged in but not allowed (HTTP 403)."""
