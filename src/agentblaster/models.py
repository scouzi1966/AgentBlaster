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


class AdapterResponse(BaseModel):
    """Raw provider response plus normalized request metadata."""

    provider: str
    contract: ApiContract
    status_code: int
    latency_ms: float
    raw: dict[str, Any] = Field(default_factory=dict)
    text: str = ""


class BenchmarkCase(BaseModel):
    """Declarative benchmark case executed by a suite runner."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str
    prompt: str
    expected_substring: str
    max_tokens: int = Field(default=32, ge=1)
    temperature: float = Field(default=0.0, ge=0.0)
    tags: list[str] = Field(default_factory=list)


class SuiteDefinition(BaseModel):
    """Named benchmark suite consisting of one or more cases."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    description: str
    cases: list[BenchmarkCase] = Field(min_length=1)


class RawTraceMode(str, Enum):
    OFF = "off"
    REDACTED = "redacted"
    FULL = "full"


class BenchmarkResult(BaseModel):
    """Single benchmark case result written to results.jsonl."""

    run_id: str
    case_id: str
    suite: str
    provider: str
    contract: ApiContract
    model: str
    ok: bool
    status_code: int | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    failure_class: str | None = None
    message: str = ""
    raw_response_path: str | None = None


class RunManifest(BaseModel):
    """Run-level metadata persisted with every benchmark execution."""

    run_id: str
    suite: str
    provider: str
    contract: ApiContract
    model: str
    raw_trace_mode: RawTraceMode
    created_at: str
    case_count: int = 0


class RunSummary(BaseModel):
    """Run-level aggregate summary."""

    run_id: str
    suite: str
    provider: str
    model: str
    total_cases: int
    passed: int
    failed: int
    results_path: str
    manifest_path: str
