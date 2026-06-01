from __future__ import annotations

import json

from agentblaster.release import build_packaging_readiness, build_release_provenance, write_release_provenance


def test_build_release_provenance_records_declared_dependencies(tmp_path) -> None:
    pyproject = {
        "project": {
            "name": "agentblaster",
            "version": "0.1.0",
            "description": "Benchmark suite",
            "requires-python": ">=3.11",
            "readme": "README.md",
            "license": {"text": "MIT"},
            "classifiers": ["Topic :: Software Development :: Testing"],
            "dependencies": ["typer>=0.12", "pydantic>=2.7"],
            "optional-dependencies": {
                "dev": ["pytest>=8.0"],
                "exports": ["pyarrow>=15.0"],
                "gui-test": ["playwright>=1.44"],
                "reports": ["cairosvg>=2.7"],
                "secrets": ["keyring>=25.0"],
            },
            "scripts": {"agentblaster": "agentblaster.cli:app"},
        },
        "build-system": {"requires": ["hatchling"], "build-backend": "hatchling.build"},
        "tool": {
            "pytest": {
                "ini_options": {
                    "markers": [
                        "unit: fast tests",
                        "contract: contract tests",
                        "integration: integration tests",
                        "security: security tests",
                        "gui: GUI tests",
                        "remote: remote tests",
                        "packaging: package tests",
                    ]
                }
            }
        },
    }
    for path in [
        "README.md",
        "docs/providers.md",
        "docs/dashboard.md",
        "docs/security-policy.md",
        "docs/release-qualification.md",
    ]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ready\n", encoding="utf-8")

    payload = build_release_provenance(
        pyproject,
        project_root=tmp_path,
        include_installed=False,
        include_source_hashes=False,
    )

    assert payload["schema"] == "agentblaster.release-provenance"
    assert payload["project"]["name"] == "agentblaster"
    assert payload["dependencies"]["declared_runtime"] == ["pydantic>=2.7", "typer>=0.12"]
    assert payload["dependencies"]["declared_optional"]["dev"] == ["pytest>=8.0"]
    assert payload["dependencies"]["declared_optional"]["exports"] == ["pyarrow>=15.0"]
    assert payload["dependencies"]["declared_optional"]["gui-test"] == ["playwright>=1.44"]
    assert payload["dependencies"]["declared_optional"]["reports"] == ["cairosvg>=2.7"]
    assert payload["dependencies"]["declared_optional"]["secrets"] == ["keyring>=25.0"]
    assert payload["dependencies"]["build_system"] == ["hatchling"]
    assert payload["dependencies"]["installed"] == []
    assert payload["sbom"]["schema_version"] == "agentblaster.sbom.v1"
    assert payload["sbom"]["format"] == "spdx-lite"
    assert payload["sbom"]["security"]["contains_secret_values"] is False
    assert payload["sbom"]["security"]["contacts_package_indexes"] is False
    assert payload["sbom"]["security"]["includes_installed_inventory"] is False
    sbom_packages = {package["name"]: package for package in payload["sbom"]["packages"]}
    assert sbom_packages["agentblaster"]["license"] == "MIT"
    assert sbom_packages["typer"]["version_spec"] == "typer>=0.12"
    assert sbom_packages["pytest"]["scope"] == "optional:dev"
    assert sbom_packages["hatchling"]["scope"] == "build-system"
    assert {
        "from": payload["sbom"]["root_package"],
        "to": sbom_packages["typer"]["spdx_id"],
        "relationship": "DEPENDS_ON",
        "scope": "runtime",
    } in payload["sbom"]["relationships"]
    assert payload["source_hashes"] == []
    assert payload["packaging_readiness"]["ok"] is True
    assert payload["packaging_readiness"]["failed"] == 0


def test_build_packaging_readiness_reports_static_gaps(tmp_path) -> None:
    pyproject = {
        "project": {
            "name": "agentblaster",
            "version": "0.1.0",
            "description": "Benchmark suite",
            "requires-python": ">=3.11",
            "dependencies": ["typer>=0.12"],
        },
        "build-system": {"requires": ["setuptools"], "build-backend": "setuptools.build_meta"},
        "tool": {"pytest": {"ini_options": {"markers": ["unit: fast tests"]}}},
    }

    readiness = build_packaging_readiness(pyproject, project_root=tmp_path)

    assert readiness["schema"] == "agentblaster.packaging-readiness"
    assert readiness["ok"] is False
    missing_by_id = {check["id"]: check["missing"] for check in readiness["checks"] if not check["ok"]}
    assert "readme" in missing_by_id["required-project-fields"]
    assert "license" in missing_by_id["license-metadata"]
    assert "hatchling.build" in missing_by_id["build-backend"]
    assert "agentblaster" in missing_by_id["cli-entrypoint"]
    assert "gui-test" in missing_by_id["optional-dependency-groups"]
    assert "exports" in missing_by_id["optional-dependency-groups"]
    assert "reports" in missing_by_id["optional-dependency-groups"]
    assert "packaging" in missing_by_id["pytest-markers"]
    assert "README.md" in missing_by_id["release-docs"]


def test_write_release_provenance_hashes_safe_project_files(tmp_path) -> None:
    (tmp_path / "src" / "agentblaster").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "agentblaster"
version = "0.1.0"
description = "Benchmark suite"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = ["typer>=0.12"]

[project.scripts]
agentblaster = "agentblaster.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# AgentBlaster\n", encoding="utf-8")
    (tmp_path / "src" / "agentblaster" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    output = tmp_path / "reports" / "release-provenance.json"

    path = write_release_provenance(output, project_root=tmp_path)

    assert path == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    hashed_paths = {item["path"] for item in payload["source_hashes"]}
    assert {"pyproject.toml", "README.md", "src/agentblaster/__init__.py"} <= hashed_paths
    assert "API_KEY" not in output.read_text(encoding="utf-8")
