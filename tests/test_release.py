from __future__ import annotations

import json

from agentblaster.release import build_release_provenance, write_release_provenance


def test_build_release_provenance_records_declared_dependencies(tmp_path) -> None:
    pyproject = {
        "project": {
            "name": "agentblaster",
            "version": "0.1.0",
            "description": "Benchmark suite",
            "requires-python": ">=3.11",
            "dependencies": ["typer>=0.12", "pydantic>=2.7"],
            "optional-dependencies": {"dev": ["pytest>=8.0"]},
        },
        "build-system": {"requires": ["hatchling"]},
    }

    payload = build_release_provenance(
        pyproject,
        project_root=tmp_path,
        include_installed=False,
        include_source_hashes=False,
    )

    assert payload["schema"] == "agentblaster.release-provenance"
    assert payload["project"]["name"] == "agentblaster"
    assert payload["dependencies"]["declared_runtime"] == ["pydantic>=2.7", "typer>=0.12"]
    assert payload["dependencies"]["declared_optional"] == {"dev": ["pytest>=8.0"]}
    assert payload["dependencies"]["build_system"] == ["hatchling"]
    assert payload["dependencies"]["installed"] == []
    assert payload["source_hashes"] == []


def test_write_release_provenance_hashes_safe_project_files(tmp_path) -> None:
    (tmp_path / "src" / "agentblaster").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "agentblaster"
version = "0.1.0"
description = "Benchmark suite"
requires-python = ">=3.11"
dependencies = ["typer>=0.12"]

[build-system]
requires = ["hatchling"]
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
