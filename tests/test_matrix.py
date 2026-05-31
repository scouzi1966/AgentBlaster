from __future__ import annotations

from agentblaster.models import RawTraceMode
from agentblaster.matrix import load_matrix_file


def test_load_matrix_file_resolves_relative_suite_file(tmp_path) -> None:
    suites_dir = tmp_path / "suites"
    suites_dir.mkdir()
    (suites_dir / "smoke.yaml").write_text(
        """
name: matrix-smoke-suite
description: Matrix smoke suite
cases:
  - id: case-one
    title: Case one
    prompt: "Reply with exactly: agentblaster-ok"
    expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )
    matrix_path = tmp_path / "matrix.yaml"
    matrix_path.write_text(
        """
name: local-matrix
runs:
  - engine: local-openai
    suite_file: suites/smoke.yaml
    model: qwen-test
    concurrency: 2
    no_raw_traces: true
""",
        encoding="utf-8",
    )

    matrix = load_matrix_file(matrix_path)

    assert matrix.name == "local-matrix"
    assert matrix.runs[0].suite_file == suites_dir / "smoke.yaml"
    assert matrix.runs[0].concurrency == 2
    assert matrix.runs[0].raw_traces == RawTraceMode.REDACTED
