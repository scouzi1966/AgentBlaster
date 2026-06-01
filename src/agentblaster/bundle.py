from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from agentblaster.errors import ConfigError
from agentblaster.integrity import INTEGRITY_FILENAME, SIGNATURE_FILENAME, load_integrity_manifest, verify_run_integrity


FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PUBLICATION_BUNDLE_ARTIFACTS = {
    "manifest.json",
    "suite.json",
    "summary.json",
    "report.html",
    "report.md",
    "publication.json",
    "report-card.svg",
    INTEGRITY_FILENAME,
    SIGNATURE_FILENAME,
}


def create_replay_bundle(
    run_dir: Path,
    *,
    output_dir: Path | None = None,
    strict: bool = False,
) -> Path:
    """Create a deterministic portable bundle from a verified run directory."""
    verification = verify_run_integrity(run_dir, allow_extra=not strict)
    if not verification.ok:
        details = []
        if verification.missing:
            details.append(f"missing={','.join(verification.missing)}")
        if verification.changed:
            details.append(f"changed={','.join(verification.changed)}")
        if verification.extra:
            details.append(f"extra={','.join(verification.extra)}")
        raise ConfigError(f"run integrity verification failed: {'; '.join(details)}")

    integrity = load_integrity_manifest(run_dir)
    target_dir = output_dir or run_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{integrity.run_id}.agentblaster.zip"

    archive_paths = sorted([INTEGRITY_FILENAME, *integrity.artifacts.keys()])
    if (run_dir / SIGNATURE_FILENAME).exists():
        archive_paths.append(SIGNATURE_FILENAME)
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for relative_path in archive_paths:
            source = _safe_artifact_path(run_dir, relative_path)
            _write_deterministic_file(archive, source, relative_path)

    return target


def create_publication_bundle(
    run_dir: Path,
    *,
    output_dir: Path | None = None,
) -> Path:
    """Create a deterministic shareable bundle containing only redacted publication artifacts."""
    verification = verify_run_integrity(run_dir, allow_extra=True)
    if not verification.ok:
        details = []
        if verification.missing:
            details.append(f"missing={','.join(verification.missing)}")
        if verification.changed:
            details.append(f"changed={','.join(verification.changed)}")
        raise ConfigError(f"run integrity verification failed: {'; '.join(details)}")

    integrity = load_integrity_manifest(run_dir)
    target_dir = output_dir or run_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{integrity.run_id}.agentblaster-publication.zip"
    archive_paths = sorted(
        artifact
        for artifact in PUBLICATION_BUNDLE_ARTIFACTS
        if (run_dir / artifact).exists()
        and (artifact == INTEGRITY_FILENAME or artifact == SIGNATURE_FILENAME or artifact in integrity.artifacts)
    )
    if "publication.json" not in archive_paths:
        raise ConfigError("publication bundle requires publication.json; run `agentblaster report --format publication` first")

    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for relative_path in archive_paths:
            source = _safe_artifact_path(run_dir, relative_path)
            _write_deterministic_file(archive, source, relative_path)
    return target


def _safe_artifact_path(run_dir: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"unsafe artifact path in integrity manifest: {relative_path}")
    source = run_dir / path
    if not source.exists():
        raise ConfigError(f"missing artifact for replay bundle: {relative_path}")
    return source


def _write_deterministic_file(archive: ZipFile, source: Path, relative_path: str) -> None:
    info = ZipInfo(relative_path, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, source.read_bytes())
