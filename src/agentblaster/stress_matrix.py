from __future__ import annotations

from typing import Iterable

import yaml

from agentblaster.errors import ConfigError
from agentblaster.matrix import MatrixDefinition, MatrixRun
from agentblaster.model_catalog import get_model_target
from agentblaster.models import RawTraceMode

DEFAULT_STRESS_SUITES = ["prefill", "trace-replay"]
DEFAULT_CONCURRENCY_LEVELS = [1, 2, 4, 8]


def generate_stress_matrix(
    *,
    providers: list[str],
    target_ids: list[str],
    suites: list[str] | None = None,
    concurrency_levels: list[int] | None = None,
    no_raw_traces: bool = True,
    raw_traces: RawTraceMode = RawTraceMode.REDACTED,
    strict_unknown_capabilities: bool = False,
    name: str | None = None,
    description: str | None = None,
) -> MatrixDefinition:
    provider_names = _clean_strings(providers, label="providers")
    targets = [get_model_target(target_id) for target_id in _clean_strings(target_ids, label="targets")]
    suite_names = _clean_strings(suites or DEFAULT_STRESS_SUITES, label="suites")
    levels = _clean_concurrency_levels(concurrency_levels or DEFAULT_CONCURRENCY_LEVELS)

    runs: list[MatrixRun] = []
    for provider in provider_names:
        for target in targets:
            for suite in suite_names:
                for concurrency in levels:
                    runs.append(
                        MatrixRun(
                            engine=provider,
                            model=target.default_model,
                            suite=suite,
                            concurrency=concurrency,
                            raw_traces=raw_traces,
                            no_raw_traces=no_raw_traces,
                            strict_unknown_capabilities=strict_unknown_capabilities,
                            model_metadata=target.metadata,
                        )
                    )
    if not runs:
        raise ConfigError("stress matrix generation produced no runs")

    matrix_name = name or _matrix_name(provider_names, [target.id for target in targets], suite_names, levels)
    return MatrixDefinition(
        name=matrix_name,
        description=description
        or (
            "AgentBlaster concurrency/prefill stress matrix for "
            f"providers={','.join(provider_names)} targets={','.join(target.id for target in targets)} "
            f"suites={','.join(suite_names)} concurrency={','.join(str(level) for level in levels)}."
        ),
        runs=runs,
    )


def stress_matrix_to_yaml(matrix: MatrixDefinition) -> str:
    return yaml.safe_dump(matrix.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=False) + "\n"


def stress_matrix_summary(matrix: MatrixDefinition) -> dict[str, object]:
    providers = sorted({run.engine for run in matrix.runs})
    suites = sorted({run.suite for run in matrix.runs})
    models = sorted({run.model or "" for run in matrix.runs})
    concurrency_levels = sorted({run.concurrency for run in matrix.runs})
    return {
        "schema_version": "agentblaster.stress-matrix-summary.v1",
        "name": matrix.name,
        "total_runs": len(matrix.runs),
        "providers": providers,
        "suites": suites,
        "models": models,
        "concurrency_levels": concurrency_levels,
        "raw_traces_disabled": all(run.no_raw_traces for run in matrix.runs),
    }


def _clean_strings(values: Iterable[str], *, label: str) -> list[str]:
    cleaned = [value.strip() for value in values if value.strip()]
    if not cleaned:
        raise ConfigError(f"at least one {label} value is required")
    return cleaned


def _clean_concurrency_levels(values: Iterable[int]) -> list[int]:
    levels = sorted({int(value) for value in values})
    if not levels:
        raise ConfigError("at least one concurrency level is required")
    invalid = [level for level in levels if level < 1]
    if invalid:
        raise ConfigError("concurrency levels must be >= 1")
    return levels


def _matrix_name(providers: list[str], targets: list[str], suites: list[str], levels: list[int]) -> str:
    provider_part = "providers" if len(providers) > 2 else "-".join(_slug(provider) for provider in providers)
    target_part = "models" if len(targets) > 2 else "-".join(_slug(target) for target in targets)
    suite_part = "suites" if len(suites) > 2 else "-".join(_slug(suite) for suite in suites)
    level_part = "c" + "-".join(str(level) for level in levels)
    return _slug(f"stress-{provider_part}-{target_part}-{suite_part}-{level_part}")[:96]


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "."} else "-" for character in value).strip("-")
