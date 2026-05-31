from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ApiContract(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    NATIVE = "native"


class SecretRef(BaseModel):
    """Reference to a secret without storing the raw secret value."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["env", "keyring"]
    name: str = Field(min_length=1)

    def display(self) -> str:
        return f"{self.kind}:{self.name}"


class ProviderConfig(BaseModel):
    """Persisted provider definition for local or remote endpoints."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    contract: ApiContract
    base_url: HttpUrl
    api_key_ref: SecretRef | None = None
    default_model: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    rate_limits: dict[str, Any] = Field(default_factory=dict)
    cost_model: dict[str, Any] = Field(default_factory=dict)
    remote: bool = False

    @field_validator("headers")
    @classmethod
    def reject_secret_header_values(cls, value: dict[str, str]) -> dict[str, str]:
        for header_name, header_value in value.items():
            lowered = header_name.lower()
            if lowered in {"authorization", "x-api-key", "api-key"}:
                raise ValueError("auth headers must be configured through api_key_ref")
            if "sk-" in header_value or "Bearer " in header_value:
                raise ValueError("header values must not contain raw API keys")
        return value


class ProvidersFile(BaseModel):
    """On-disk provider registry."""

    version: int = 1
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class ProbeResult(BaseModel):
    """Normalized provider probe result."""

    provider: str
    contract: ApiContract
    ok: bool
    status_code: int | None = None
    message: str
    models: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
