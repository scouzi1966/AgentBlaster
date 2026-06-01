from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from agentblaster.errors import ConfigError
from agentblaster.launch_recipes import list_launch_recipe_templates
from agentblaster.model_catalog import MODEL_TARGETS
from agentblaster.presets import PROVIDER_PRESETS
from agentblaster.suites import BUILTIN_SUITES


RECOMMENDED_MODEL_TARGETS = ("qwen3.6-27b-dense", "gemma-4-31b-dense")
RECOMMENDED_BASELINE_SUITES = (
    "smoke",
    "structured",
    "toolcall",
    "toolsim",
    "agentic-tool-loop",
    "trace-replay",
    "agent-fanout",
    "prefill",
    "cache-control",
    "harness-engineering",
    "cancellation",
)
REPRESENTATIVE_AGENT_PROFILES = ("opencode", "openclaw", "hermes", "pi")
STANDARD_WORKFLOW_SURFACES = (
    "openai-anthropic-tool-calling",
    "mcp-fixtures",
    "skill-packs",
    "lcp-emerging",
    "harness-engineering",
)
STANDARD_PREFILL_CHALLENGES = (
    "large repeated system prompts",
    "large tool schemas and deterministic MCP catalogs",
    "skill-pack and LCP context prefixes",
    "prompt-cache reuse, suffix mutation, and invalidation behavior",
)
STANDARD_CONCURRENCY_CHALLENGES = (
    "agent fan-out bursts",
    "subagent and tool-loop scheduling",
    "queue fairness under repeated static prefixes",
    "cancellation isolation for long-running local requests",
)
STANDARD_STATS_CLAIM_POLICY = (
    "Use contract-conformant OpenAI or Anthropic responses for baseline compatibility comparisons.",
    "Use harness-measured latency, TTFT, cancellation, and tool-loop validators when provider-native stats are absent.",
    "Use native telemetry only through an explicit telemetry profile and metric coverage claim contract.",
    "Record unsupported native metrics as null or unsupported; do not infer publishable native prefill/cache stats.",
)


@dataclass(frozen=True)
class EngineTarget:
    id: str
    display_name: str
    lifecycle: str
    platform_focus: str
    provider_presets: tuple[str, ...]
    launch_recipes: tuple[str, ...]
    contracts: tuple[str, ...]
    telemetry_profiles: tuple[str, ...]
    recommended_model_targets: tuple[str, ...]
    recommended_suites: tuple[str, ...]
    comparison_axes: tuple[str, ...]
    readiness_checks: tuple[str, ...]
    risk_notes: tuple[str, ...]
    security_notes: tuple[str, ...]


ENGINE_TARGETS: tuple[EngineTarget, ...] = (
    EngineTarget(
        id="afm-mlx",
        display_name="AFM MLX",
        lifecycle="primary",
        platform_focus="macOS Apple Silicon first; benchmark results remain comparable through OpenAI-compatible HTTP contracts.",
        provider_presets=("afm",),
        launch_recipes=("afm",),
        contracts=("openai",),
        telemetry_profiles=("afm-mlx-openai-compatible",),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=RECOMMENDED_BASELINE_SUITES,
        comparison_axes=(
            "TTFT and prefill throughput under repeated static prompts",
            "cache reuse and invalidation behavior",
            "tool-call envelope correctness",
            "concurrency scaling and queue fairness",
        ),
        readiness_checks=(
            "Render launch recipe and provider add command",
            "Run provider probe and contract check against the selected model",
            "Generate metric coverage and telemetry mapping reports",
            "Run Qwen/Gemma matrix smoke before stress suites",
        ),
        risk_notes=(
            "MLX model artifact naming and quantization must be recorded in model metadata.",
            "Prompt-cache metrics must be distinguished from generic OpenAI usage when native stats are available.",
        ),
        security_notes=(
            "Local loopback provider by default",
            "No API key required for local AFM unless operator configures a gateway",
            "Raw traces should remain disabled or redacted for shareable reports",
        ),
    ),
    EngineTarget(
        id="mlx-lm",
        display_name="MLX-LM",
        lifecycle="reference-local",
        platform_focus="macOS Apple Silicon local reference implementation.",
        provider_presets=("mlx-lm",),
        launch_recipes=("mlx-lm",),
        contracts=("openai",),
        telemetry_profiles=("mlx-lm-openai-compatible",),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=(
            "smoke",
            "structured",
            "toolcall",
            "agent-fanout",
            "prefill",
            "cache-control",
            "harness-engineering",
        ),
        comparison_axes=(
            "OpenAI-compatible baseline behavior",
            "large prefix handling",
            "tool and JSON envelope compatibility",
        ),
        readiness_checks=(
            "Confirm mlx-lm server flags for the installed version",
            "Run contract check before comparing quality or throughput",
            "Record exact model artifact and chat template metadata",
        ),
        risk_notes=("Telemetry may be sparse unless wrapper-specific stats are exposed.",),
        security_notes=("Loopback endpoint by default", "No host tools are executed by benchmark cases"),
    ),
    EngineTarget(
        id="ollama-mlx",
        display_name="Ollama / Ollama Native",
        lifecycle="external-local",
        platform_focus="Cross-platform local engine; native stats are available through Ollama-specific responses.",
        provider_presets=("ollama", "ollama-native"),
        launch_recipes=("ollama", "ollama-native"),
        contracts=("openai", "native"),
        telemetry_profiles=("generic-openai-chat", "ollama-native"),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=RECOMMENDED_BASELINE_SUITES,
        comparison_axes=(
            "OpenAI-compatible behavior versus native metric fidelity",
            "nanosecond timing conversion for prompt/decode stats",
            "concurrency and queue fairness",
        ),
        readiness_checks=(
            "Pull or map provider-specific Ollama model names before matrix generation",
            "Prefer ollama-native for timing comparisons",
            "Run contract check separately for OpenAI-compatible and native profiles",
        ),
        risk_notes=(
            "Ollama model names may not match Hugging Face or MLX artifact names.",
            "Native durations are nanoseconds and must be normalized before comparison.",
        ),
        security_notes=("Local endpoint by default", "Model pulls are operator actions and not executed by AgentBlaster recipes"),
    ),
    EngineTarget(
        id="rapid-mlx",
        display_name="Rapid MLX",
        lifecycle="candidate-local",
        platform_focus="macOS Apple Silicon local engine exposed through OpenAI-compatible HTTP.",
        provider_presets=("rapid-mlx",),
        launch_recipes=("rapid-mlx",),
        contracts=("openai",),
        telemetry_profiles=("rapid-mlx-openai-compatible",),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=(
            "smoke",
            "structured",
            "toolcall",
            "agent-fanout",
            "prefill",
            "cache-control",
            "harness-engineering",
        ),
        comparison_axes=(
            "OpenAI-compatible contract fidelity",
            "prefill and cache diagnostics when optional stats are exposed",
            "tool-call and structured-output behavior",
        ),
        readiness_checks=(
            "Review installed Rapid MLX serve command and flags",
            "Run provider contract check before matrix inclusion",
            "Capture optional stats in raw_stats for future mappings",
        ),
        risk_notes=("Command names and response stats may vary by installed Rapid MLX version.",),
        security_notes=("Loopback endpoint by default", "No API key expected unless wrapped by a gateway"),
    ),
    EngineTarget(
        id="omlx",
        display_name="oMLX",
        lifecycle="candidate-local",
        platform_focus="macOS Apple Silicon local engine exposed through OpenAI-compatible HTTP.",
        provider_presets=("omlx",),
        launch_recipes=("omlx",),
        contracts=("openai",),
        telemetry_profiles=("omlx-openai-compatible",),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=(
            "smoke",
            "structured",
            "toolcall",
            "agent-fanout",
            "prefill",
            "cache-control",
            "harness-engineering",
        ),
        comparison_axes=(
            "OpenAI-compatible contract fidelity",
            "large system prompt behavior",
            "agentic tool-call compatibility",
        ),
        readiness_checks=(
            "Review installed oMLX serve command and flags",
            "Run contract check before quality comparisons",
            "Record missing native stats as null rather than inferred",
        ),
        risk_notes=("Native telemetry mapping is intentionally conservative until oMLX stats are standardized.",),
        security_notes=("Loopback endpoint by default", "No benchmark case should execute host tools"),
    ),
    EngineTarget(
        id="vllm-mlx",
        display_name="vLLM-MLX",
        lifecycle="candidate-local",
        platform_focus="macOS Apple Silicon MLX-backed vLLM-compatible local server exposed through OpenAI-compatible and Anthropic-compatible HTTP.",
        provider_presets=("vllm-mlx", "vllm-mlx-anthropic"),
        launch_recipes=("vllm-mlx", "vllm-mlx-anthropic"),
        contracts=("openai", "anthropic"),
        telemetry_profiles=("generic-openai-chat", "anthropic-messages"),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=(
            "smoke",
            "structured",
            "toolcall",
            "agent-fanout",
            "prefill",
            "cache-control",
            "harness-engineering",
        ),
        comparison_axes=(
            "OpenAI-compatible server behavior under local MLX-backed serving",
            "prefill sensitivity for long repeated system and tool prompts",
            "batching, queueing, and concurrency scaling under agent fanout",
        ),
        readiness_checks=(
            "Confirm the installed vLLM-MLX package, entrypoint, and supported model artifact format",
            "Run provider contract check before matrix inclusion",
            "Record missing native stats as unavailable until vLLM-MLX exposes a stable local stats schema",
        ),
        risk_notes=(
            "vLLM-MLX packaging and CLI flags may vary by upstream version.",
            "Telemetry should remain generic OpenAI-compatible until native MLX/vLLM timing fields are standardized.",
        ),
        security_notes=("Loopback endpoint by default", "No API key expected unless wrapped by a gateway"),
    ),
    EngineTarget(
        id="lm-studio",
        display_name="LM Studio",
        lifecycle="external-local",
        platform_focus="Cross-platform desktop/local server with OpenAI-compatible, Responses-compatible, and optional native surfaces.",
        provider_presets=("lm-studio", "lm-studio-responses", "lm-studio-anthropic", "lm-studio-native"),
        launch_recipes=("lm-studio", "lm-studio-responses", "lm-studio-anthropic", "lm-studio-native"),
        contracts=("openai", "openai-responses", "anthropic", "native"),
        telemetry_profiles=("generic-openai-chat", "openai-responses", "anthropic-messages", "lm-studio-native"),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=RECOMMENDED_BASELINE_SUITES,
        comparison_axes=(
            "contract surface parity across Chat/Responses/native modes",
            "TTFT and decode throughput when native stats are available",
            "dashboard launch and report usability",
        ),
        readiness_checks=(
            "Confirm the loaded model in the LM Studio GUI or CLI",
            "Run separate contract checks for Chat, Responses, and native profiles when enabled",
            "Use native profile only when version exposes the expected stats surface",
        ),
        risk_notes=(
            "Loaded model and server mode can diverge from provider config if changed in the GUI.",
            "Native stats availability varies by version and endpoint mode.",
        ),
        security_notes=("Local endpoint by default", "GUI screenshots must use redacted fixtures for release evidence"),
    ),
    EngineTarget(
        id="remote-openai-compatible",
        display_name="Remote OpenAI-Compatible API",
        lifecycle="remote-contract",
        platform_focus="Any platform with network access and an OpenAI-compatible HTTPS endpoint.",
        provider_presets=("openai", "openai-responses"),
        launch_recipes=(),
        contracts=("openai", "openai-responses"),
        telemetry_profiles=("generic-openai-chat", "openai-responses"),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=(
            "smoke",
            "structured",
            "toolcall",
            "toolsim",
            "trace-replay",
            "agent-fanout",
            "harness-engineering",
        ),
        comparison_axes=(
            "contract and tool-call compatibility",
            "remote budget and rate-limit policy behavior",
            "usage accounting comparability",
        ),
        readiness_checks=(
            "Store API key through environment, optional OS keyring, or explicit dotenv fallback reference",
            "Require explicit remote policy before dispatch",
            "Configure cost model and rate limits before non-smoke runs",
        ),
        risk_notes=("Remote endpoints can incur cost and data egress; they should never run under offline policy.",),
        security_notes=(
            "Use api_key_ref only; raw auth headers are rejected",
            "Enterprise policy should enforce remote opt-in, cost ceilings, TLS verification, and redaction",
        ),
    ),
    EngineTarget(
        id="remote-anthropic-compatible",
        display_name="Remote Anthropic-Compatible API",
        lifecycle="remote-contract",
        platform_focus="Any platform with network access and an Anthropic Messages-compatible HTTPS endpoint.",
        provider_presets=("anthropic",),
        launch_recipes=(),
        contracts=("anthropic",),
        telemetry_profiles=("anthropic-messages",),
        recommended_model_targets=RECOMMENDED_MODEL_TARGETS,
        recommended_suites=("smoke", "toolcall", "toolsim", "trace-replay", "agent-fanout", "cache-control", "cancellation"),
        comparison_axes=(
            "Anthropic tool envelope compatibility",
            "cache read/write token accounting",
            "remote budget and rate-limit policy behavior",
        ),
        readiness_checks=(
            "Store API key through environment, optional OS keyring, or explicit dotenv fallback reference",
            "Require explicit remote policy before dispatch",
            "Run cache-control only with reviewed cost and retention settings",
        ),
        risk_notes=("Anthropic-style prompt caching reports cache creation and read tokens separately from generic Chat usage.",),
        security_notes=(
            "Use api_key_ref only; raw x-api-key headers are rejected",
            "Enterprise policy should enforce remote opt-in, cost ceilings, TLS verification, and redaction",
        ),
    ),
)


def list_engine_targets() -> list[dict[str, Any]]:
    return [engine_target_payload(target) for target in ENGINE_TARGETS]


def get_engine_target(target_id: str) -> dict[str, Any]:
    for target in ENGINE_TARGETS:
        if target.id == target_id:
            return engine_target_payload(target)
    available = ", ".join(target.id for target in ENGINE_TARGETS)
    raise ConfigError(f"unknown engine target: {target_id}; available targets: {available}")


def get_engine_target_for_provider(provider_name: str) -> dict[str, Any] | None:
    """Return the engine target associated with a known provider preset or target id."""

    normalized = provider_name.strip()
    if not normalized:
        return None
    for target in ENGINE_TARGETS:
        if normalized == target.id or normalized in target.provider_presets:
            return engine_target_payload(target)
    return None


def compact_engine_target_for_provider(provider_name: str) -> dict[str, Any] | None:
    target = get_engine_target_for_provider(provider_name)
    if target is None:
        return None
    standardization = target["standardization"]
    return {
        "id": target["id"],
        "display_name": target["display_name"],
        "lifecycle": target["lifecycle"],
        "contracts": target["contracts"],
        "telemetry_profiles": target["telemetry_profiles"],
        "recommended_model_targets": target["recommended_model_targets"],
        "recommended_suites": target["recommended_suites"],
        "standardization": {
            "primary_scoring_contract": standardization["primary_scoring_contract"],
            "contract_priority": standardization["contract_priority"],
            "workflow_surfaces": standardization["workflow_surfaces"],
            "representative_agent_profiles": standardization["representative_agent_profiles"],
            "prefill_challenges": standardization["prefill_challenges"],
            "concurrency_challenges": standardization["concurrency_challenges"],
            "native_telemetry_profiles": standardization["native_telemetry_profiles"],
            "native_metrics_policy": standardization["native_metrics_policy"],
        },
    }


def engine_target_catalog() -> dict[str, Any]:
    targets = list_engine_targets()
    return {
        "schema_version": "agentblaster.engine-target-catalog.v1",
        "boundary": "Engine targets are static benchmark planning metadata; they do not prove an engine is installed, reachable, or compatible.",
        "recommended_model_targets": list(RECOMMENDED_MODEL_TARGETS),
        "recommended_baseline_suites": list(RECOMMENDED_BASELINE_SUITES),
        "representative_agent_profiles": list(REPRESENTATIVE_AGENT_PROFILES),
        "standard_workflow_surfaces": list(STANDARD_WORKFLOW_SURFACES),
        "standardization": {
            "baseline_contract_policy": "OpenAI-compatible Chat remains the primary cross-engine baseline when available; Responses, Anthropic, and native contracts are measured as explicit additional surfaces.",
            "prefill_challenges": list(STANDARD_PREFILL_CHALLENGES),
            "concurrency_challenges": list(STANDARD_CONCURRENCY_CHALLENGES),
            "stats_claim_policy": list(STANDARD_STATS_CLAIM_POLICY),
            "agent_profile_baseline": list(REPRESENTATIVE_AGENT_PROFILES),
        },
        "targets": targets,
        "summary": {
            "target_count": len(targets),
            "primary_target": "afm-mlx",
            "local_target_count": sum(1 for target in targets if not target["remote_contract"]),
            "remote_contract_count": sum(1 for target in targets if target["remote_contract"]),
            "all_declared_presets_available": all(target["preset_coverage"]["all_available"] for target in targets),
            "all_declared_launch_recipes_available": all(target["launch_recipe_coverage"]["all_available"] for target in targets),
        },
    }


def engine_target_catalog_json() -> str:
    return json.dumps(engine_target_catalog(), indent=2, sort_keys=True) + "\n"


def format_engine_target_catalog(markdown: bool = False) -> str:
    catalog = engine_target_catalog()
    if markdown:
        lines = [
            "# AgentBlaster Engine Target Catalog",
            "",
            f"Schema: `{catalog['schema_version']}`",
            "",
            catalog["boundary"],
            "",
            "## Targets",
            "",
        ]
        for target in catalog["targets"]:
            lines.extend(
                [
                    f"### `{target['id']}`",
                    "",
                    f"- Display name: {target['display_name']}",
                    f"- Lifecycle: `{target['lifecycle']}`",
                    f"- Contracts: {', '.join(f'`{item}`' for item in target['contracts'])}",
                    f"- Provider presets: {', '.join(f'`{item}`' for item in target['provider_presets']) or '`none`'}",
                    f"- Launch recipes: {', '.join(f'`{item}`' for item in target['launch_recipes']) or '`none`'}",
                    f"- Telemetry profiles: {', '.join(f'`{item}`' for item in target['telemetry_profiles'])}",
                    f"- Primary scoring contract: `{target['standardization']['primary_scoring_contract']}`",
                    f"- Workflow surfaces: {', '.join(f'`{item}`' for item in target['standardization']['workflow_surfaces'])}",
                    f"- Agent profiles: {', '.join(f'`{item}`' for item in target['standardization']['representative_agent_profiles'])}",
                    f"- Recommended suites: {', '.join(f'`{item}`' for item in target['recommended_suites'])}",
                    "- Readiness checks: " + "; ".join(target["readiness_checks"]),
                    "- Risk notes: " + "; ".join(target["risk_notes"]),
                    "",
                ]
            )
        return "\n".join(lines)

    lines = ["AgentBlaster engine target catalog", f"targets: {catalog['summary']['target_count']}"]
    for target in catalog["targets"]:
        lines.append(
            f"- {target['id']} ({'/'.join(target['contracts'])}): presets={','.join(target['provider_presets']) or 'none'} telemetry={','.join(target['telemetry_profiles'])}"
        )
    return "\n".join(lines) + "\n"


def engine_target_payload(target: EngineTarget) -> dict[str, Any]:
    payload = asdict(target)
    payload["provider_presets"] = list(target.provider_presets)
    payload["launch_recipes"] = list(target.launch_recipes)
    payload["contracts"] = list(target.contracts)
    payload["telemetry_profiles"] = list(target.telemetry_profiles)
    payload["recommended_model_targets"] = list(target.recommended_model_targets)
    payload["recommended_suites"] = list(target.recommended_suites)
    payload["comparison_axes"] = list(target.comparison_axes)
    payload["readiness_checks"] = list(target.readiness_checks)
    payload["risk_notes"] = list(target.risk_notes)
    payload["security_notes"] = list(target.security_notes)
    payload["remote_contract"] = target.lifecycle == "remote-contract"
    payload["standardization"] = _target_standardization(target)
    payload["preset_coverage"] = _coverage(target.provider_presets, set(PROVIDER_PRESETS))
    payload["launch_recipe_coverage"] = _coverage(target.launch_recipes, {recipe.engine for recipe in list_launch_recipe_templates()})
    payload["model_target_coverage"] = _coverage(target.recommended_model_targets, set(MODEL_TARGETS))
    payload["suite_coverage"] = _coverage(target.recommended_suites, set(BUILTIN_SUITES))
    return payload


def _target_standardization(target: EngineTarget) -> dict[str, Any]:
    primary_scoring_contract = _primary_scoring_contract(target)
    native_profiles = tuple(profile for profile in target.telemetry_profiles if profile.endswith("-native") or profile in {"ollama-native", "lm-studio-native"})
    return {
        "primary_scoring_contract": primary_scoring_contract,
        "contract_priority": list(_contract_priority(target, primary_scoring_contract)),
        "workflow_surfaces": list(STANDARD_WORKFLOW_SURFACES),
        "representative_agent_profiles": list(REPRESENTATIVE_AGENT_PROFILES),
        "prefill_challenges": list(STANDARD_PREFILL_CHALLENGES),
        "concurrency_challenges": list(STANDARD_CONCURRENCY_CHALLENGES),
        "stats_claim_policy": list(STANDARD_STATS_CLAIM_POLICY),
        "native_telemetry_profiles": list(native_profiles),
        "native_metrics_policy": _native_metrics_policy(native_profiles),
        "security_boundary": "static planning metadata only; no launches, probes, provider calls, model-cache reads, or secret reads",
    }


def _primary_scoring_contract(target: EngineTarget) -> str:
    if "openai" in target.contracts:
        return "openai"
    return target.contracts[0] if target.contracts else "none"


def _contract_priority(target: EngineTarget, primary_scoring_contract: str) -> tuple[str, ...]:
    ordered = [primary_scoring_contract]
    ordered.extend(contract for contract in target.contracts if contract != primary_scoring_contract)
    return tuple(ordered)


def _native_metrics_policy(native_profiles: tuple[str, ...]) -> str:
    if native_profiles:
        return "Native stats may support publication claims only through the listed telemetry profiles and metric coverage claim contract."
    return "Native stats are not assumed; publish harness-measured and contract usage metrics unless a future explicit telemetry profile is added."


def _coverage(items: tuple[str, ...], available: set[str]) -> dict[str, Any]:
    missing = [item for item in items if item not in available]
    return {
        "declared": list(items),
        "missing": missing,
        "all_available": not missing,
    }
