from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class ApiContract(str, Enum):
    OPENAI = "openai"
    OPENAI_RESPONSES = "openai-responses"
    ANTHROPIC = "anthropic"
    NATIVE = "native"


class EnvironmentSnapshot(BaseModel):
    """Privacy-preserving runtime environment metadata for reproducibility."""

    model_config = ConfigDict(extra="forbid")

    agentblaster_version: str | None = None
    python_version: str | None = None
    platform: str | None = None
    platform_release: str | None = None
    platform_version: str | None = None
    os: str | None = None
    architecture: str | None = None
    machine: str | None = None
    processor: str | None = None
    cpu_count: int | None = None
    memory_total_bytes: int | None = None
    ci: bool = False
    hostname_sha256: str | None = None


class SecretRef(BaseModel):
    """Reference to a secret without storing the raw secret value."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["env", "keyring"]
    name: str = Field(min_length=1)

    def display(self) -> str:
        return f"{self.kind}:{self.name}"


class ModelMetadata(BaseModel):
    """Optional model identity metadata used to keep benchmark comparisons honest."""

    model_config = ConfigDict(extra="forbid")

    revision: str | None = None
    architecture: str | None = None
    quantization: str | None = None
    tokenizer: str | None = None
    chat_template: str | None = None
    context_length: int | None = Field(default=None, ge=1)

    def is_empty(self) -> bool:
        return not any(
            [
                self.revision,
                self.architecture,
                self.quantization,
                self.tokenizer,
                self.chat_template,
                self.context_length,
            ]
        )


class ProviderRunMetadata(BaseModel):
    """Provider and adapter identity captured with a run and compact result rows."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    base_url_host: str | None = None
    remote: bool = False
    native_adapter: str | None = None
    adapter_name: str | None = None
    adapter_version: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    metrics_url_host: str | None = None
    tls_verify: bool = True
    ca_bundle: str | None = None


class ProviderConfig(BaseModel):
    """Persisted provider definition for local or remote endpoints."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    contract: ApiContract
    base_url: HttpUrl
    api_key_ref: SecretRef | None = None
    default_model: str | None = None
    model_metadata: ModelMetadata = Field(default_factory=ModelMetadata)
    headers: dict[str, str] = Field(default_factory=dict)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    rate_limits: dict[str, Any] = Field(default_factory=dict)
    cost_model: dict[str, Any] = Field(default_factory=dict)
    metrics_url: HttpUrl | None = None
    tls_verify: bool = True
    ca_bundle: Path | None = None
    native_adapter: str | None = None
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

    @field_validator("base_url")
    @classmethod
    def reject_base_url_secrets(cls, value: HttpUrl) -> HttpUrl:
        _reject_url_secrets(str(value), "base_url")
        return value

    @field_validator("metrics_url")
    @classmethod
    def reject_metrics_url_secrets(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is None:
            return value
        _reject_url_secrets(str(value), "metrics_url")
        return value

    @model_validator(mode="after")
    def reject_conflicting_tls_settings(self) -> "ProviderConfig":
        if not self.tls_verify and self.ca_bundle is not None:
            raise ValueError("ca_bundle requires tls_verify to remain enabled")
        return self


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


class ToolCallRecord(BaseModel):
    """Normalized provider-emitted tool call."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    valid: bool = True


class SimulatedToolResult(BaseModel):
    """Deterministic safe tool result produced by the benchmark harness."""

    tool_name: str
    ok: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AdapterResponse(BaseModel):
    """Raw provider response plus normalized request metadata."""

    provider: str
    contract: ApiContract
    status_code: int
    latency_ms: float
    raw: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    tool_names: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    streaming: bool = False
    ttft_ms: float | None = None


class TraceMessage(BaseModel):
    """Normalized multi-turn message used for trace replay across provider contracts."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkCase(BaseModel):
    """Declarative benchmark case executed by a suite runner."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str
    prompt: str
    scenario: str | None = None
    messages: list[TraceMessage] = Field(default_factory=list)
    provenance: Literal[
        "primary_source",
        "public_benchmark_adapted",
        "synthetic_representative",
        "internal_regression",
        "customer_trace_sanitized",
    ] = "synthetic_representative"
    source_url: str | None = None
    license: str | None = None
    risk_level: Literal["low", "medium", "high"] = "low"
    expected_substring: str | None = None
    expected_json_fields: dict[str, Any] = Field(default_factory=dict)
    expected_tool_name: str | None = None
    system_prompt: str | None = None
    cache_control: dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: str | dict[str, Any] | None = None
    previous_response_id: str | None = None
    max_tool_calls: int | None = Field(default=None, ge=1)
    simulated_tools: list[str] = Field(default_factory=list)
    expected_tool_result_substring: str | None = None
    mcp_profile: str | None = None
    lcp_profile: str | None = None
    skills: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=3600.0)
    streaming: bool = False
    max_tokens: int = Field(default=32, ge=1)
    temperature: float = Field(default=0.0, ge=0.0)
    tags: list[str] = Field(default_factory=list)


class SuiteProvenance(BaseModel):
    """Suite-level provenance used for reproducible reporting and dataset hygiene."""

    model_config = ConfigDict(extra="forbid")

    origin: Literal[
        "builtin",
        "user_file",
        "harness_generated",
        "primary_source",
        "public_benchmark_adapted",
        "synthetic_representative",
        "internal_regression",
        "customer_trace_sanitized",
        "unknown",
    ] = "unknown"
    source_suite: str | None = None
    generator: str | None = None
    generator_profile: str | None = None
    generator_seed: int | None = None
    generator_repeats: int | None = None
    primary_source: str | None = None
    source_url: str | None = None
    license: str | None = None
    risk_labels: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SuiteDefinition(BaseModel):
    """Named benchmark suite consisting of one or more cases."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    description: str
    provenance: SuiteProvenance = Field(default_factory=SuiteProvenance)
    cases: list[BenchmarkCase] = Field(min_length=1)


class RawTraceMode(str, Enum):
    OFF = "off"
    REDACTED = "redacted"
    FULL = "full"


class RetentionPolicy(BaseModel):
    """Run artifact retention metadata for governance and cleanup planning."""

    model_config = ConfigDict(extra="forbid")

    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    retain_days: int | None = Field(default=None, ge=0)
    raw_trace_retain_days: int | None = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)


class BenchmarkResult(BaseModel):
    """Single benchmark case result written to results.jsonl."""

    run_id: str
    case_id: str
    case_title: str | None = None
    scenario: str | None = None
    case_tags: list[str] = Field(default_factory=list)
    case_provenance: str | None = None
    case_risk_level: str | None = None
    case_source_url: str | None = None
    case_license: str | None = None
    suite: str
    provider: str
    contract: ApiContract
    model: str
    ok: bool
    provider_endpoint_host: str | None = None
    provider_remote: bool | None = None
    native_adapter: str | None = None
    adapter_name: str | None = None
    adapter_version: str | None = None
    status_code: int | None = None
    request_started_at: str | None = None
    request_completed_at: str | None = None
    queue_ms: float | None = None
    rate_limit_wait_ms: float | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_hit_ratio: float | None = None
    input_cost_usd: float | None = None
    output_cost_usd: float | None = None
    cache_read_cost_usd: float | None = None
    cache_write_cost_usd: float | None = None
    request_cost_usd: float | None = None
    total_cost_usd: float | None = None
    ttft_ms: float | None = None
    load_ms: float | None = None
    prompt_eval_ms: float | None = None
    decode_ms: float | None = None
    tokens_per_second_prefill: float | None = None
    tokens_per_second_decode: float | None = None
    raw_usage: dict[str, Any] = Field(default_factory=dict)
    raw_stats: dict[str, Any] = Field(default_factory=dict)
    tool_calls_requested: int | None = None
    tool_calls_emitted: int | None = None
    tool_calls_valid: int | None = None
    structured_output_valid: bool | None = None
    finish_reason: str | None = None
    simulated_tool_results: list[SimulatedToolResult] = Field(default_factory=list)
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
    concurrency: int = 1
    suite_sha256: str | None = None
    case_sha256: dict[str, str] = Field(default_factory=dict)
    suite_snapshot_path: str | None = None
    suite_provenance: SuiteProvenance = Field(default_factory=SuiteProvenance)
    metrics_artifacts: list[str] = Field(default_factory=list)
    provider_metadata: ProviderRunMetadata = Field(default_factory=ProviderRunMetadata)
    environment: EnvironmentSnapshot = Field(default_factory=EnvironmentSnapshot)
    model_metadata: ModelMetadata = Field(default_factory=ModelMetadata)
    retention_policy: RetentionPolicy = Field(default_factory=RetentionPolicy)


class RunIntegrityManifest(BaseModel):
    """Checksums for completed run artifacts."""

    run_id: str
    algorithm: Literal["sha256"] = "sha256"
    created_at: str
    artifacts: dict[str, str] = Field(default_factory=dict)


class RunIntegrityVerification(BaseModel):
    """Result of verifying a run integrity manifest."""

    run_id: str
    ok: bool
    checked: int = 0
    missing: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)


class RunSignatureManifest(BaseModel):
    """HMAC attestation over a run integrity manifest."""

    run_id: str
    algorithm: Literal["hmac-sha256"] = "hmac-sha256"
    signed_integrity_algorithm: Literal["sha256"] = "sha256"
    created_at: str
    key_id: str
    signature: str
    signed_artifacts: dict[str, str] = Field(default_factory=dict)


class RunSignatureVerification(BaseModel):
    """Result of verifying a run signature and its underlying integrity manifest."""

    run_id: str
    ok: bool
    signature_ok: bool
    integrity_ok: bool
    key_id: str
    checked: int = 0
    missing: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Run-level aggregate summary."""

    run_id: str
    suite: str
    provider: str
    model: str
    total_cases: int
    passed: int
    failed: int
    concurrency: int = 1
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    requests_per_second: float | None = None
    results_path: str
    manifest_path: str


def _reject_url_secrets(url: str, field_name: str) -> None:
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not contain embedded credentials")
    query = parsed.query.lower()
    if any(marker in query for marker in ("token=", "api_key=", "apikey=", "password=", "secret=")):
        raise ValueError(f"{field_name} must not contain credential query parameters")
