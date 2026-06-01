from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from agentblaster.errors import ConfigError


ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
RAW_ARTIFACT_NAMES = {"results.jsonl"}


def create_release_qualification_bundle(
    *,
    name: str,
    output_dir: Path,
    evidence_bundles: list[Path] | None = None,
    comparison_gates: list[Path] | None = None,
    matrix_gates: list[Path] | None = None,
    release_provenance: Path | None = None,
    publication_bundles: list[Path] | None = None,
    selftest_reports: list[Path] | None = None,
) -> Path:
    """Create a deterministic redaction-safe release qualification package."""

    artifact_specs: list[tuple[str, Path]] = []
    for path in evidence_bundles or []:
        artifact_specs.append(("evidence", path))
    for path in comparison_gates or []:
        artifact_specs.append(("gates/comparison", path))
    for path in matrix_gates or []:
        artifact_specs.append(("gates/matrix", path))
    if release_provenance is not None:
        artifact_specs.append(("release", release_provenance))
    for path in publication_bundles or []:
        artifact_specs.append(("publication", path))
    for path in selftest_reports or []:
        artifact_specs.append(("selftest", path))

    if not artifact_specs:
        raise ConfigError("release qualification bundle requires at least one artifact")

    normalized_name = _safe_name(name)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{normalized_name}.agentblaster-release-qualification.zip"
    entries: dict[str, bytes] = {}
    manifest_artifacts = []
    for category, path in artifact_specs:
        source = path.resolve()
        _validate_artifact(category, source)
        archive_path = f"{category}/{source.name}"
        data = source.read_bytes()
        entries[archive_path] = data
        manifest_artifacts.append(
            {
                "category": category,
                "source_path": str(path),
                "archive_path": archive_path,
                "sha256": sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )

    manifest = {
        "schema": "agentblaster.release-qualification-bundle",
        "schema_version": 1,
        "name": normalized_name,
        "created_at": _utc_now(),
        "artifact_count": len(manifest_artifacts),
        "artifacts": sorted(manifest_artifacts, key=lambda item: item["archive_path"]),
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "contains_results_jsonl": False,
            "notes": "Release qualification bundles should contain only redacted evidence, gate, publication, provenance, and selftest artifacts.",
        },
    }
    entries["manifest.json"] = _json_bytes(manifest)

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for archive_path, data in sorted(entries.items()):
            info = ZipInfo(archive_path, ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return output


def _validate_artifact(category: str, path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise ConfigError(f"missing release qualification artifact: {path}")
    parts = {part.lower() for part in path.parts}
    if "raw" in parts or path.name in RAW_ARTIFACT_NAMES:
        raise ConfigError(f"raw run artifacts are not allowed in release qualification bundles: {path}")
    if path.suffix == ".zip":
        if category == "evidence" and not path.name.endswith(".agentblaster-evidence.zip"):
            raise ConfigError(f"evidence bundle must end with .agentblaster-evidence.zip: {path}")
        if category == "publication" and not path.name.endswith(".agentblaster-publication.zip"):
            raise ConfigError(f"publication bundle must end with .agentblaster-publication.zip: {path}")
        if category not in {"evidence", "publication"}:
            raise ConfigError(f"zip artifact is not allowed for category {category}: {path}")


def _safe_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in name).strip("-")
    return cleaned or "release-qualification"


def _json_bytes(payload) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
