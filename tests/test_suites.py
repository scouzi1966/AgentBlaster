from __future__ import annotations

import pytest

from agentblaster.errors import ConfigError
from agentblaster.suites import BUILTIN_SUITES, load_suite_file, validate_case_or_suite_file


def test_builtin_suites_include_core_mvp_families() -> None:
    assert {"smoke", "structured", "toolcall", "prefill"}.issubset(BUILTIN_SUITES)


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
    expected_substring: agentblaster-ok
""",
        encoding="utf-8",
    )

    suite = load_suite_file(path)

    assert suite.name == "local-smoke"
    assert suite.cases[0].id == "case-one"


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
