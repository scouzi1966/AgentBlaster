from __future__ import annotations

import json
from zipfile import ZipFile

import pytest

from agentblaster.errors import ConfigError
from agentblaster.release_qualification import create_release_qualification_bundle


def test_create_release_qualification_bundle_packages_allowed_artifacts(tmp_path) -> None:
    evidence = tmp_path / "suite.agentblaster-evidence.zip"
    matrix_gate = tmp_path / "matrix-gate.json"
    comparison_gate = tmp_path / "comparison-gate.json"
    provenance = tmp_path / "release-provenance.json"
    publication = tmp_path / "run.agentblaster-publication.zip"
    selftest = tmp_path / "selftest-report.json"
    for path in [evidence, publication]:
        path.write_bytes(b"zip-data")
    for path in [matrix_gate, comparison_gate, provenance, selftest]:
        path.write_text('{"ok": true}
', encoding="utf-8")

    output = create_release_qualification_bundle(
        name="afm-release",
        output_dir=tmp_path / "release-bundles",
        evidence_bundles=[evidence],
        comparison_gates=[comparison_gate],
        matrix_gates=[matrix_gate],
        release_provenance=provenance,
        publication_bundles=[publication],
        selftest_reports=[selftest],
    )

    assert output.name == "afm-release.agentblaster-release-qualification.zip"
    with ZipFile(output) as archive:
        names = sorted(archive.namelist())
        assert names == [
            "evidence/suite.agentblaster-evidence.zip",
            "gates/comparison/comparison-gate.json",
            "gates/matrix/matrix-gate.json",
            "manifest.json",
            "publication/run.agentblaster-publication.zip",
            "release/release-provenance.json",
            "selftest/selftest-report.json",
        ]
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["schema"] == "agentblaster.release-qualification-bundle"
    assert manifest["artifact_count"] == 6
    assert manifest["security"]["contains_raw_traces"] is False


def test_create_release_qualification_bundle_rejects_raw_results(tmp_path) -> None:
    raw_results = tmp_path / "results.jsonl"
    raw_results.write_text("{}
", encoding="utf-8")

    with pytest.raises(ConfigError, match="raw run artifacts are not allowed"):
        create_release_qualification_bundle(
            name="bad-release",
            output_dir=tmp_path / "release-bundles",
            matrix_gates=[raw_results],
        )
