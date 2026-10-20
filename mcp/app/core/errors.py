"""Domain errors shared by services and their transport adapters."""


class NotFoundError(LookupError):
    """Raised when a requested light, collection, scene, or schedule is absent."""
