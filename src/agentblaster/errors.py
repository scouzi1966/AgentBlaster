from __future__ import annotations


class AgentBlasterError(Exception):
    """Base exception for user-facing AgentBlaster failures."""


class ConfigError(AgentBlasterError):
    """Raised when persisted configuration is invalid or unavailable."""


class SecretError(AgentBlasterError):
    """Raised when a secret cannot be stored or resolved safely."""


class AdapterError(AgentBlasterError):
    """Raised when a provider adapter cannot complete a request."""


class PolicyError(AgentBlasterError):
    """Raised when a run violates configured enterprise policy."""
