from __future__ import annotations

import shutil
from pathlib import Path

from agentblaster.errors import ConfigError


def cleanup_run(
    run_dir: Path,
    *,
    raw: bool = True,
    reports: bool = False,
    exports: bool = False,
    all_artifacts: bool = False,
) -> list[Path]:
    if not run_dir.exists():
        raise ConfigError(f"run directory does not exist: {run_dir}")

    removed: list[Path] = []
    if all_artifacts:
        shutil.rmtree(run_dir)
        return [run_dir]

    if raw:
        removed.extend(_remove_path(run_dir / "raw"))
    if reports:
        removed.extend(_remove_path(run_dir / "report.html"))
        removed.extend(_remove_path(run_dir / "summary.json"))
    if exports:
        removed.extend(_remove_path(run_dir / "exports"))
    return removed


def _remove_path(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return [path]
