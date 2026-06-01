from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.suites import BUILTIN_SUITES, load_suite_file, validate_case_or_suite_file


def test_builtin_suites_include_core_mvp_families() -> None:
    assert {"smoke", "structured", "toolcall", "prefill", "toolsim", "trace-replay", "lcp-context"}.issubset(BUILTIN_SUITES)


def test_load_suite_file(tmp_path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(
        """
name: local-smoke
description: Local smoke suite
cases:
  - id: case-one
    title: Case one
    prompt: "Reply with exactly: agentblaster-ok"
    provenance: internal_regression
    risk_level: low
    mcp_profile: fixture-mcp
    lcp_profile: fixture-lcp
    skills:
      - repo-triage
    metrics:
      - ttft_ms
    timeout_seconds: 12.5
    expected_substring: agentblaster-ok
    simulated_tools:
      - search_docs
    messages:
      - role: system
        content: Trace policy.
      - role: user
        content: Read fixture context.
""",
        encoding="utf-8",
    )

    suite = load_suite_file(path)

    assert suite.name == "local-smoke"
    assert suite.provenance.origin == "user_file"
    assert suite.provenance.primary_source == "user-provided suite file"
    assert suite.cases[0].id == "case-one"
    assert suite.cases[0].simulated_tools == ["search_docs"]
    assert suite.cases[0].provenance == "internal_regression"
    assert suite.cases[0].lcp_profile == "fixture-lcp"
    assert suite.cases[0].skills == ["repo-triage"]
    assert suite.cases[0].timeout_seconds == 12.5
    assert suite.cases[0].messages[0].role == "system"
    assert suite.cases[0].messages[1].content == "Read fixture context."


def test_builtin_suites_carry_builtin_provenance() -> None:
    suite = BUILTIN_SUITES["smoke"]

    assert suite.provenance.origin == "builtin"
    assert suite.provenance.primary_source == "AgentBlaster"
    assert suite.provenance.license == "MIT"


def test_validate_case_or_suite_file_accepts_single_case(tmp_path) -> None:
    path = tmp_path / "case.yaml"
    path.write_text(
        """
id: case-one
title: Case one
prompt: "Reply with exactly: agentblaster-ok"
expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )

    assert validate_case_or_suite_file(path) == "valid case case-one"


def test_validate_case_or_suite_file_rejects_invalid_yaml(tmp_path) -> None:
    path = tmp_path / "case.yaml"
    path.write_text("id: bad\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid benchmark case"):
        validate_case_or_suite_file(path)
