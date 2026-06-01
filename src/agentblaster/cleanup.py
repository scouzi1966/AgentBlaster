from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentblaster.errors import ConfigError
from agentblaster.models import RunManifest


CACHE_ARTIFACT_DIRS = ("cache", "caches", ".cache", "prompt-cache", "prompt-caches")
TEMP_ARTIFACT_DIRS = ("tmp", "temp")
BUNDLE_ARTIFACT_DIRS = ("publication-bundles", "matrix-publication-bundles", "release-bundles", "evidence-bundles")
BUNDLE_ARTIFACT_PATTERNS = (
    "*.agentblaster-publication.zip",
    "*.agentblaster-matrix-publication.zip",
    "*.agentblaster-release-qualification.zip",
    "*.agentblaster-evidence.zip",
)
CLEANUP_PLAN_SCHEMA_VERSION = "agentblaster.cleanup-plan.v1"
RETENTION_CLEANUP_SCHEMA_VERSION = "agentblaster.retention-cleanup.v1"


def cleanup_run(
    run_dir: Path,
    *,
    raw: bool = True,
    reports: bool = False,
    exports: bool = False,
    caches: bool = False,
    temp: bool = False,
    bundles: bool = False,
    all_artifacts: bool = False,
) -> list[Path]:
    planned = plan_cleanup_run(
        run_dir,
        raw=raw,
        reports=reports,
        exports=exports,
        caches=caches,
        temp=temp,
        bundles=bundles,
        all_artifacts=all_artifacts,
    )
    for path in planned:
        _delete_path(path)
    return planned


def plan_cleanup_run(
    run_dir: Path,
    *,
    raw: bool = True,
    reports: bool = False,
    exports: bool = False,
    caches: bool = False,
    temp: bool = False,
    bundles: bool = False,
    all_artifacts: bool = False,
) -> list[Path]:
    if not run_dir.exists():
        raise ConfigError(f"run directory does not exist: {run_dir}")

    planned: list[Path] = []
    if all_artifacts:
        return [run_dir]

    if raw:
        planned.extend(_existing_path(run_dir / "raw"))
    if reports:
        planned.extend(_existing_path(run_dir / "report.html"))
        planned.extend(_existing_path(run_dir / "report.md"))
        planned.extend(_existing_path(run_dir / "report.pdf"))
        planned.extend(_existing_path(run_dir / "report-card.svg"))
        planned.extend(_existing_path(run_dir / "report-card.png"))
        planned.extend(_existing_path(run_dir / "publication.json"))
        planned.extend(_existing_path(run_dir / "summary.json"))
    if exports:
        planned.extend(_existing_path(run_dir / "exports"))
    if caches:
        for dirname in CACHE_ARTIFACT_DIRS:
            planned.extend(_existing_path(run_dir / dirname))
    if temp:
        for dirname in TEMP_ARTIFACT_DIRS:
            planned.extend(_existing_path(run_dir / dirname))
    if bundles:
        for dirname in BUNDLE_ARTIFACT_DIRS:
            planned.extend(_existing_path(run_dir / dirname))
        for pattern in BUNDLE_ARTIFACT_PATTERNS:
            for path in sorted(run_dir.glob(pattern)):
                planned.extend(_existing_path(path))
    return planned


class ExpiredCleanupAction(BaseModel):
    """Planned cleanup action derived from run retention metadata."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_dir: Path
    action: Literal["raw", "run"]
    reason: str
    created_at: str
    expired_at: str
    classification: str
    retain_days: int | None = None
    raw_trace_retain_days: int | None = None
    removed: list[str] = Field(default_factory=list)


def plan_expired_cleanup(runs_dir: Path, *, now: datetime | None = None) -> list[ExpiredCleanupAction]:
    """Plan retention cleanup actions without deleting artifacts."""
    current_time = _aware_utc(now or datetime.now(UTC))
    if not runs_dir.exists():
        return []

    actions: list[ExpiredCleanupAction] = []
    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        manifest = _load_manifest_if_valid(run_dir)
        if manifest is None:
            continue
        try:
            created_at = _parse_datetime(manifest.created_at)
        except ValueError:
            continue
        retention = manifest.retention_policy
        if retention.retain_days is not None:
            expired_at = created_at + timedelta(days=retention.retain_days)
            if expired_at <= current_time:
                actions.append(
                    _cleanup_action(
                        manifest,
                        run_dir,
                        action="run",
                        reason=f"run retention expired after {retention.retain_days} day(s)",
                        expired_at=expired_at,
                    )
                )
                continue
        if retention.raw_trace_retain_days is not None and (run_dir / "raw").exists():
            expired_at = created_at + timedelta(days=retention.raw_trace_retain_days)
            if expired_at <= current_time:
                actions.append(
                    _cleanup_action(
                        manifest,
                        run_dir,
                        action="raw",
                        reason=f"raw trace retention expired after {retention.raw_trace_retain_days} day(s)",
                        expired_at=expired_at,
                    )
                )
    return actions


def apply_expired_cleanup(actions: list[ExpiredCleanupAction]) -> list[ExpiredCleanupAction]:
    """Apply planned cleanup actions and return actions annotated with removed paths."""
    applied: list[ExpiredCleanupAction] = []
    for action in actions:
        if action.action == "run":
            removed = cleanup_run(action.run_dir, all_artifacts=True)
        else:
            removed = cleanup_run(action.run_dir, raw=True, reports=False, exports=False)
        applied.append(action.model_copy(update={"removed": [str(path) for path in removed]}))
    return applied


def _existing_path(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [path]


def _delete_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _load_manifest_if_valid(run_dir: Path) -> RunManifest | None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cleanup_action(
    manifest: RunManifest,
    run_dir: Path,
    *,
    action: Literal["raw", "run"],
    reason: str,
    expired_at: datetime,
) -> ExpiredCleanupAction:
    retention = manifest.retention_policy
    return ExpiredCleanupAction(
        run_id=manifest.run_id,
        run_dir=run_dir,
        action=action,
        reason=reason,
        created_at=manifest.created_at,
        expired_at=expired_at.isoformat(),
        classification=retention.classification,
        retain_days=retention.retain_days,
        raw_trace_retain_days=retention.raw_trace_retain_days,
    )
