from __future__ import annotations

import json
from zipfile import ZipFile

from agentblaster.config import ProviderStore
from agentblaster.evidence import create_evidence_bundle
from agentblaster.models import ApiContract, ProviderConfig


def test_create_evidence_bundle_contains_static_review_artifacts(tmp_path) -> None:
    project_root = tmp_path / "project"
    (project_root / "src" / "agentblaster").mkdir(parents=True)
    (project_root / "pyproject.toml").write_text(
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
    (project_root / "README.md").write_text("# AgentBlaster\n", encoding="utf-8")
    (project_root / "src" / "agentblaster" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        """
name: evidence-suite
description: Evidence suite
cases:
  - id: evidence-case
    title: Evidence case
    prompt: Use the deterministic fixture tool.
    simulated_tools:
      - search_docs
""".lstrip(),
        encoding="utf-8",
    )
    policy_path = tmp_path / "agentblaster.policy.yaml"
    policy_path.write_text("allow_remote_providers: false\n", encoding="utf-8")

    path = create_evidence_bundle(
        output_dir=tmp_path / "evidence",
        suite_file=suite_path,
        policy=policy_path,
        project_root=project_root,
    )

    assert path.name == "evidence-suite.agentblaster-evidence.zip"
    with ZipFile(path) as archive:
        names = sorted(archive.namelist())
        assert names == [
            "catalogs/mcp-profiles.json",
            "catalogs/simulated-tools.json",
            "catalogs/skills.json",
            "manifest.json",
            "policy.yaml",
            "release-provenance.json",
            "suite-audit.json",
        ]
        manifest = json.loads(archive.read("manifest.json"))
        suite_audit = json.loads(archive.read("suite-audit.json"))
        simulated_tools = json.loads(archive.read("catalogs/simulated-tools.json"))
    assert manifest["schema"] == "agentblaster.evidence-bundle"
    assert manifest["security"]["contains_raw_secrets"] is False
    assert suite_audit["suite"] == "evidence-suite"
    assert suite_audit["capability_surfaces"]["simulated_tools"] == ["search_docs"]
    assert simulated_tools["catalog"] == "agentblaster.simulated-tools"


def test_create_evidence_bundle_can_include_redacted_provider_audit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTBLASTER_HOME", str(tmp_path / "home"))
    ProviderStore().upsert(
        ProviderConfig(
            name="remote-gateway",
            contract=ApiContract.OPENAI,
            base_url="https://gateway.example.com/v1",
            remote=True,
        )
    )
    project_root = tmp_path / "project"
    (project_root / "src" / "agentblaster").mkdir(parents=True)
    (project_root / "pyproject.toml").write_text(
        """
[project]
name = "agentblaster"
version = "0.1.0"
description = "Benchmark suite"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
""".strip()
        + "
",
        encoding="utf-8",
    )
    (project_root / "README.md").write_text("# AgentBlaster
", encoding="utf-8")
    (project_root / "src" / "agentblaster" / "__init__.py").write_text('__version__ = "0.1.0"
', encoding="utf-8")
    policy_path = tmp_path / "agentblaster.policy.yaml"
    policy_path.write_text("allow_remote_providers: true
require_api_key_for_remote_providers: true
", encoding="utf-8")

    path = create_evidence_bundle(
        output_dir=tmp_path / "evidence",
        suite="smoke",
        policy=policy_path,
        project_root=project_root,
        include_provider_audit=True,
    )

    with ZipFile(path) as archive:
        names = sorted(archive.namelist())
        assert "provider-audit.json" in names
        manifest = json.loads(archive.read("manifest.json"))
        provider_audit = json.loads(archive.read("provider-audit.json"))
    assert manifest["includes_provider_audit"] is True
    assert manifest["security"]["contains_redacted_provider_audit"] is True
    assert provider_audit["providers"][0]["name"] == "remote-gateway"
    assert provider_audit["providers"][0]["api_key_ref_kind"] is None
