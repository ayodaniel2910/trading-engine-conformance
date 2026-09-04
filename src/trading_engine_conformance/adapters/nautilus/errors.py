"""Fail-closed adapter exceptions."""


class NautilusAdapterError(RuntimeError):
    """Base error for the optional adapter."""


class NautilusEnvironmentError(NautilusAdapterError):
    """The installed runtime or wheel does not match the pinned candidate."""


class NautilusSemanticError(NautilusAdapterError):
    """A neutral value cannot be represented without changing its meaning."""


class NautilusInputError(NautilusAdapterError):
    """An input is mutable, unverified, outside its root, or malformed."""


class NautilusNetworkDeniedError(NautilusAdapterError):
    """The offline worker observed an attempted network operation."""
