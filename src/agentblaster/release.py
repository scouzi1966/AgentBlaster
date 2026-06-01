from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from importlib import metadata
import json
import platform
from pathlib import Path
import sys
import tomllib
from typing import Any

from agentblaster import __version__
from agentblaster.errors import ConfigError


PROVENANCE_SCHEMA_VERSION = 1
DEFAULT_HASHED_PATHS = [
    "pyproject.toml",
    "README.md",
    "agentblaster.policy.example.yaml",
    "src/agentblaster/__init__.py",
]


def write_release_provenance(
    output: Path,
    *,
    project_root: Path | None = None,
    include_installed: bool = False,
    include_source_hashes: bool = True,
) -> Path:
    """Write a redaction-safe release provenance and lightweight SBOM artifact."""

    root = (project_root or Path.cwd()).resolve()
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        raise ConfigError(f"pyproject.toml not found at project root: {root}")

    pyproject = _load_pyproject(pyproject_path)
    payload = build_release_provenance(
        pyproject,
        project_root=root,
        include_installed=include_installed,
        include_source_hashes=include_source_hashes,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def build_release_provenance(
    pyproject: dict[str, Any],
    *,
    project_root: Path,
    include_installed: bool = False,
    include_source_hashes: bool = True,
) -> dict[str, Any]:
    project = pyproject.get("project", {})
    optional_dependencies = project.get("optional-dependencies", {})
    build_system = pyproject.get("build-system", {})
    declared_dependencies = sorted(str(item) for item in project.get("dependencies", []))
    declared_optional = {
        str(group): sorted(str(item) for item in values)
        for group, values in sorted(optional_dependencies.items())
    }

    payload: dict[str, Any] = {
        "schema": "agentblaster.release-provenance",
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "agentblaster_version": __version__,
        "project": {
            "name": project.get("name"),
            "version": project.get("version"),
            "description": project.get("description"),
            "requires_python": project.get("requires-python"),
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "dependencies": {
            "declared_runtime": declared_dependencies,
            "declared_optional": declared_optional,
            "build_system": sorted(str(item) for item in build_system.get("requires", [])),
            "installed": [],
        },
        "source_hashes": [],
        "security_notes": [
            "Artifact excludes environment variables, API keys, provider configs, run traces, raw responses, and dashboard state.",
            "Dependency entries are package names/specifiers only; vulnerability status must be produced by a dedicated scanner.",
        ],
    }

    if include_installed:
        payload["dependencies"]["installed"] = _installed_components()

    if include_source_hashes:
        payload["source_hashes"] = _source_hashes(project_root)

    return payload


def _load_pyproject(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid pyproject.toml at {path}: {exc}") from exc


def _source_hashes(project_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for relative_path in DEFAULT_HASHED_PATHS:
        path = project_root / relative_path
        if not path.exists() or not path.is_file():
            continue
        data = path.read_bytes()
        entries.append(
            {
                "path": relative_path,
                "sha256": sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    return entries


def _installed_components() -> list[dict[str, str]]:
    components = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name:
            continue
        components.append({"name": name, "version": version})
    return sorted(components, key=lambda item: (item["name"].lower(), item["version"]))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
