from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentblaster.errors import ConfigError
from agentblaster.models import ModelMetadata, RawTraceMode, RetentionPolicy


class MatrixRun(BaseModel):
    """Single run entry in a benchmark matrix file."""

    model_config = ConfigDict(extra="forbid")

    engine: str = Field(min_length=1)
    model: str | None = None
    suite: str = "smoke"
    suite_file: Path | None = None
    concurrency: int = Field(default=1, ge=1)
    raw_traces: RawTraceMode = RawTraceMode.REDACTED
    no_raw_traces: bool = False
    capability_preflight: bool = True
    strict_unknown_capabilities: bool = False
    model_metadata: ModelMetadata = Field(default_factory=ModelMetadata)
    retention_policy: RetentionPolicy = Field(default_factory=RetentionPolicy)


class MatrixDefinition(BaseModel):
    """Declarative matrix containing one or more benchmark runs."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    description: str = ""
    runs: list[MatrixRun] = Field(min_length=1)


class MatrixExecutionRunSummary(BaseModel):
    """Machine-readable summary for one attempted matrix run entry."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    engine: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str
    suite: str
    suite_file: str | None = None
    run_id: str | None = None
    ok: bool
    total_cases: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    concurrency: int = Field(ge=1)
    results_path: str | None = None
    manifest_path: str | None = None
    summary_path: str | None = None
    error_type: str | None = None
    error_message: str | None = None


class MatrixExecutionSummary(BaseModel):
    """Machine-readable artifact for an executed benchmark matrix."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    matrix_name: str
    matrix_path: str
    description: str = ""
    created_at: str
    dry_run: bool = False
    continue_on_error: bool = False
    total_runs: int = Field(ge=0)
    attempted_runs: int = Field(default=0, ge=0)
    completed_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    runs: list[MatrixExecutionRunSummary] = Field(default_factory=list)


def load_matrix_file(path: Path) -> MatrixDefinition:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid matrix file at {path}: {exc}") from exc

    try:
        matrix = MatrixDefinition.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid matrix definition at {path}: {exc}") from exc

    base_dir = path.parent
    resolved_runs: list[MatrixRun] = []
    for run in matrix.runs:
        if run.suite_file is not None and not run.suite_file.is_absolute():
            run = run.model_copy(update={"suite_file": base_dir / run.suite_file})
        resolved_runs.append(run)
    return matrix.model_copy(update={"runs": resolved_runs})
