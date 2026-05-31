from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentblaster.errors import ConfigError, PolicyError
from agentblaster.models import ProviderConfig, RawTraceMode


class SecurityPolicy(BaseModel):
    """Enterprise policy controls enforced before benchmark execution."""

    model_config = ConfigDict(extra="forbid")

    allowed_providers: set[str] | None = None
    allowed_base_url_hosts: set[str] | None = None
    allow_remote_providers: bool = True
    allow_full_raw_traces: bool = False
    max_prompt_tokens: int | None = Field(default=None, ge=1)
    max_concurrency: int | None = Field(default=None, ge=1)


def load_policy(path: Path | None) -> SecurityPolicy:
    if path is None:
        return SecurityPolicy()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return SecurityPolicy.model_validate(data)
    except (OSError, ValidationError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid policy file at {path}: {exc}") from exc


def enforce_provider_policy(
    provider: ProviderConfig,
    policy: SecurityPolicy,
    *,
    raw_trace_mode: RawTraceMode,
) -> None:
    if policy.allowed_providers is not None and provider.name not in policy.allowed_providers:
        raise PolicyError(f"provider is not allowed by policy: {provider.name}")

    if provider.remote and not policy.allow_remote_providers:
        raise PolicyError(f"remote providers are disabled by policy: {provider.name}")

    host = urlparse(str(provider.base_url)).hostname
    if policy.allowed_base_url_hosts is not None and host not in policy.allowed_base_url_hosts:
        raise PolicyError(f"base URL host is not allowed by policy: {host}")

    if raw_trace_mode is RawTraceMode.FULL and not policy.allow_full_raw_traces:
        raise PolicyError("full raw traces are disabled by policy")


def offline_policy() -> SecurityPolicy:
    return SecurityPolicy(allow_remote_providers=False)
