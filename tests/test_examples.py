from __future__ import annotations

from pathlib import Path

from agentblaster.matrix import load_matrix_file


def test_qwen_gemma_stress_example_covers_agentic_stress_axes() -> None:
    matrix = load_matrix_file(Path("examples/matrices/qwen-gemma-stress.yaml"))

    assert matrix.name == "qwen-gemma-stress"
    assert len(matrix.runs) == 40
    assert {run.engine for run in matrix.runs} == {"afm", "lm-studio"}
    assert {run.suite for run in matrix.runs} == {
        "agentic-tool-loop",
        "agent-fanout",
        "prefill",
        "harness-engineering",
        "trace-replay",
    }
    assert {run.concurrency for run in matrix.runs} == {1, 4}
    assert {run.model_metadata.architecture for run in matrix.runs} == {"qwen3.6-dense", "gemma-4-dense"}
    assert all(run.no_raw_traces for run in matrix.runs)
    assert all(run.strict_unknown_capabilities for run in matrix.runs)
