"""Fail-closed exceptions for the quarantined vectorbt screener."""


class VectorbtAdapterError(RuntimeError):
    """Base error for the optional stage-zero adapter."""


class VectorbtEnvironmentError(VectorbtAdapterError):
    """The optional dependency stack is absent or outside the accepted pins."""


class VectorbtInputError(VectorbtAdapterError):
    """A screening input is malformed, mutable, unverified, or outside its root."""


class VectorbtNetworkDeniedError(VectorbtAdapterError):
    """The offline worker observed an attempted network operation."""


class VectorbtLedgerError(VectorbtAdapterError):
    """A trial ledger is incomplete, duplicated, inconsistent, or tampered."""
