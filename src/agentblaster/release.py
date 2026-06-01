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
SBOM_SCHEMA_VERSION = "agentblaster.sbom.v1"
DEFAULT_HASHED_PATHS = [
    "pyproject.toml",
    "README.md",
    "agentblaster.policy.example.yaml",
    "src/agentblaster/__init__.py",
]
REQUIRED_PROJECT_FIELDS = [
    "name",
    "version",
    "description",
    "readme",
    "requires-python",
]
REQUIRED_OPTIONAL_DEPENDENCY_GROUPS = ["dev", "exports", "gui-test", "reports", "secrets"]
REQUIRED_PYTEST_MARKERS = ["unit", "contract", "integration", "security", "gui", "remote", "packaging"]
REQUIRED_RELEASE_DOCS = [
    "README.md",
    "docs/providers.md",
    "docs/dashboard.md",
    "docs/security-policy.md",
    "docs/release-qualification.md",
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


def write_packaging_readiness(output: Path, *, project_root: Path | None = None) -> Path:
    """Write a static packaging readiness report without building or installing the package."""

    root = (project_root or Path.cwd()).resolve()
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        raise ConfigError(f"pyproject.toml not found at project root: {root}")
    payload = build_packaging_readiness(_load_pyproject(pyproject_path), project_root=root)
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
    declared_build_system = sorted(str(item) for item in build_system.get("requires", []))
    installed_components = _installed_components() if include_installed else []

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
            "build_system": declared_build_system,
            "installed": installed_components,
        },
        "sbom": _build_sbom(
            project=project,
            declared_runtime=declared_dependencies,
            declared_optional=declared_optional,
            declared_build_system=declared_build_system,
            installed=installed_components,
        ),
        "packaging_readiness": build_packaging_readiness(pyproject, project_root=project_root),
        "source_hashes": [],
        "security_notes": [
            "Artifact excludes environment variables, API keys, provider configs, run traces, raw responses, and dashboard state.",
            "Dependency entries are package names/specifiers only; vulnerability status must be produced by a dedicated scanner.",
        ],
    }

    if include_source_hashes:
        payload["source_hashes"] = _source_hashes(project_root)

    return payload


def format_packaging_readiness(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster packaging readiness",
        f"ok: {str(report['ok']).lower()}",
        f"passed: {report['passed']}",
        f"failed: {report['failed']}",
        "checks:",
    ]
    for check in report["checks"]:
        status = "PASS" if check["ok"] else "FAIL"
        missing = ",".join(check["missing"]) if check["missing"] else "-"
        lines.append(f"- {status} {check['id']}: missing={missing}")
    return "\n".join(lines) + "\n"


def build_packaging_readiness(pyproject: dict[str, Any], *, project_root: Path) -> dict[str, Any]:
    project = pyproject.get("project", {})
    optional_dependencies = project.get("optional-dependencies", {})
    build_system = pyproject.get("build-system", {})
    pytest_options = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})

    checks = [
        _readiness_check(
            "required-project-fields",
            "Project metadata includes required package fields.",
            [field for field in REQUIRED_PROJECT_FIELDS if project.get(field)],
            REQUIRED_PROJECT_FIELDS,
        ),
        _readiness_check(
            "license-metadata",
            "Project declares license metadata for package consumers.",
            ["license"] if project.get("license") else [],
            ["license"],
        ),
        _readiness_check(
            "classifiers",
            "Project declares package classifiers for index/catalog consumers.",
            ["classifiers"] if project.get("classifiers") else [],
            ["classifiers"],
        ),
        _readiness_check(
            "build-backend",
            "Build system declares hatchling backend and build requirement.",
            [
                "hatchling"
                for requirement in build_system.get("requires", [])
                if str(requirement).startswith("hatchling")
            ]
            + (["hatchling.build"] if build_system.get("build-backend") == "hatchling.build" else []),
            ["hatchling", "hatchling.build"],
        ),
        _readiness_check(
            "cli-entrypoint",
            "Package exposes the agentblaster console script.",
            ["agentblaster"] if project.get("scripts", {}).get("agentblaster") == "agentblaster.cli:app" else [],
            ["agentblaster"],
        ),
        _readiness_check(
            "optional-dependency-groups",
            "Package declares optional extras for development, result exports, GUI testing, media report rendering, and OS keyring support.",
            [group for group in REQUIRED_OPTIONAL_DEPENDENCY_GROUPS if group in optional_dependencies],
            REQUIRED_OPTIONAL_DEPENDENCY_GROUPS,
        ),
        _readiness_check(
            "pytest-markers",
            "Test harness declares SDLC markers including packaging and GUI tiers.",
            _present_pytest_markers(pytest_options),
            REQUIRED_PYTEST_MARKERS,
        ),
        _readiness_check(
            "release-docs",
            "Release and enterprise readiness documentation is present.",
            [path for path in REQUIRED_RELEASE_DOCS if (project_root / path).exists()],
            REQUIRED_RELEASE_DOCS,
        ),
    ]
    passed = sum(1 for check in checks if check["ok"])
    return {
        "schema": "agentblaster.packaging-readiness",
        "schema_version": 1,
        "ok": passed == len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "notes": [
            "Readiness is static and does not build wheels, install packages, import optional dependencies, or contact package indexes.",
            "Run the packaging selftest tier before publishing release artifacts.",
        ],
    }


def _readiness_check(check_id: str, description: str, present: list[str], required: list[str]) -> dict[str, Any]:
    present_set = set(present)
    missing = [item for item in required if item not in present_set]
    return {
        "id": check_id,
        "description": description,
        "ok": not missing,
        "present": sorted(present_set),
        "missing": missing,
    }


def _present_pytest_markers(pytest_options: dict[str, Any]) -> list[str]:
    markers = pytest_options.get("markers", [])
    present = []
    if isinstance(markers, list):
        for marker in markers:
            name = str(marker).split(":", 1)[0].strip()
            if name:
                present.append(name)
    return present


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


def _build_sbom(
    *,
    project: dict[str, Any],
    declared_runtime: list[str],
    declared_optional: dict[str, list[str]],
    declared_build_system: list[str],
    installed: list[dict[str, str]],
) -> dict[str, Any]:
    root_name = str(project.get("name") or "agentblaster")
    root_version = str(project.get("version") or "unknown")
    root_id = _sbom_id(root_name, root_version)
    packages = [
        {
            "spdx_id": root_id,
            "name": root_name,
            "version": root_version,
            "type": "application",
            "scope": "root",
            "source": "project",
            "license": _license_text(project.get("license")),
            "supplier": "NOASSERTION",
            "download_location": "NOASSERTION",
        }
    ]
    relationships = []
    seen = {root_id}
    for spec in declared_runtime:
        package = _declared_dependency_package(spec, scope="runtime", source="project.dependencies")
        if package["spdx_id"] not in seen:
            packages.append(package)
            seen.add(package["spdx_id"])
        relationships.append({"from": root_id, "to": package["spdx_id"], "relationship": "DEPENDS_ON", "scope": "runtime"})
    for group, specs in sorted(declared_optional.items()):
        for spec in specs:
            package = _declared_dependency_package(
                spec,
                scope=f"optional:{group}",
                source=f"project.optional-dependencies.{group}",
            )
            if package["spdx_id"] not in seen:
                packages.append(package)
                seen.add(package["spdx_id"])
            relationships.append(
                {"from": root_id, "to": package["spdx_id"], "relationship": "OPTIONAL_DEPENDS_ON", "scope": group}
            )
    for spec in declared_build_system:
        package = _declared_dependency_package(spec, scope="build-system", source="build-system.requires")
        if package["spdx_id"] not in seen:
            packages.append(package)
            seen.add(package["spdx_id"])
        relationships.append(
            {"from": root_id, "to": package["spdx_id"], "relationship": "BUILD_DEPENDS_ON", "scope": "build-system"}
        )
    for component in installed:
        name = str(component.get("name") or "")
        version = str(component.get("version") or "")
        if not name:
            continue
        package = {
            "spdx_id": _sbom_id(name, version or "installed"),
            "name": name,
            "version": version,
            "type": "library",
            "scope": "installed-inventory",
            "source": "importlib.metadata",
            "license": "NOASSERTION",
            "supplier": "NOASSERTION",
            "download_location": "NOASSERTION",
        }
        if package["spdx_id"] not in seen:
            packages.append(package)
            seen.add(package["spdx_id"])
        relationships.append(
            {
                "from": root_id,
                "to": package["spdx_id"],
                "relationship": "ENVIRONMENT_CONTAINS",
                "scope": "installed-inventory",
            }
        )
    return {
        "schema_version": SBOM_SCHEMA_VERSION,
        "format": "spdx-lite",
        "document_name": f"{root_name}-{root_version}-sbom",
        "root_package": root_id,
        "package_count": len(packages),
        "relationship_count": len(relationships),
        "packages": packages,
        "relationships": relationships,
        "security": {
            "contains_environment_variables": False,
            "contains_secret_values": False,
            "contains_provider_configs": False,
            "contacts_package_indexes": False,
            "includes_installed_inventory": bool(installed),
        },
        "notes": [
            "SPDX-lite data is derived from pyproject declarations and optional local installed-package metadata.",
            "This artifact is an inventory, not a vulnerability scan or license legal opinion.",
        ],
    }


def _declared_dependency_package(spec: str, *, scope: str, source: str) -> dict[str, str]:
    name = _requirement_name(spec)
    return {
        "spdx_id": _sbom_id(name, spec),
        "name": name,
        "version_spec": spec,
        "type": "library",
        "scope": scope,
        "source": source,
        "license": "NOASSERTION",
        "supplier": "NOASSERTION",
        "download_location": "NOASSERTION",
    }


def _requirement_name(spec: str) -> str:
    cleaned = spec.strip()
    name_chars = []
    for char in cleaned:
        if char.isalnum() or char in {"-", "_", "."}:
            name_chars.append(char)
            continue
        break
    return "".join(name_chars) or cleaned or "unknown"


def _license_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("file") or "NOASSERTION")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "NOASSERTION"


def _sbom_id(name: str, version_or_spec: str) -> str:
    raw = f"SPDXRef-Package-{name}-{version_or_spec}"
    cleaned = "".join(char if char.isalnum() or char in {"-", "."} else "-" for char in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "SPDXRef-Package-unknown"


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
