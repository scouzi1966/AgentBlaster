from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentblaster.errors import ConfigError
from agentblaster.models import RawTraceMode


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


class MatrixDefinition(BaseModel):
    """Declarative matrix containing one or more benchmark runs."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    description: str = ""
    runs: list[MatrixRun] = Field(min_length=1)


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
