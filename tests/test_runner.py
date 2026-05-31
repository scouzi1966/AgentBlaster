from __future__ import annotations

import json

from agentblaster.models import AdapterResponse, ApiContract, ProviderConfig, RawTraceMode
from agentblaster.runner import SmokeRunner, normalize_usage


class FakeAdapter:
    def __init__(self, response: AdapterResponse) -> None:
        self.response = response

    def smoke_chat(self, model: str) -> AdapterResponse:
        return self.response


def test_normalize_openai_usage() -> None:
    assert normalize_usage(
        ApiContract.OPENAI,
        {"usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}},
    ) == (10, 4, 14)


def test_normalize_anthropic_usage_includes_cache_tokens() -> None:
    assert normalize_usage(
        ApiContract.ANTHROPIC,
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 4,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 3,
            }
        },
    ) == (10, 4, 37)


def test_smoke_runner_writes_manifest_result_and_redacted_raw(tmp_path) -> None:
    provider = ProviderConfig(
        name="openai-like",
        contract=ApiContract.OPENAI,
        base_url="https://example.com/v1",
        remote=True,
    )
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=12.3456,
        text="agentblaster-ok",
        raw={
            "choices": [{"message": {"content": "agentblaster-ok"}}],
            "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz"},
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        },
    )

    result = SmokeRunner(
        provider,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.REDACTED,
    ).run(model="qwen-test")

    run_dir = tmp_path / result.run_id
    assert result.ok is True
    assert result.input_tokens == 5
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "results.jsonl").exists()
    assert result.raw_response_path == "raw/protocol-smoke-chat.response.json"

    raw_payload = json.loads((run_dir / result.raw_response_path).read_text())
    assert raw_payload["headers"]["Authorization"] == "[REDACTED]"


def test_smoke_runner_can_disable_raw_traces(tmp_path) -> None:
    provider = ProviderConfig(name="openai-like", contract=ApiContract.OPENAI, base_url="https://example.com/v1")
    response = AdapterResponse(
        provider="openai-like",
        contract=ApiContract.OPENAI,
        status_code=200,
        latency_ms=1.0,
        text="agentblaster-ok",
        raw={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    )

    result = SmokeRunner(
        provider,
        adapter=FakeAdapter(response),  # type: ignore[arg-type]
        output_dir=tmp_path,
        raw_trace_mode=RawTraceMode.OFF,
    ).run(model="qwen-test")

    assert result.raw_response_path is None
    assert not (tmp_path / result.run_id / "raw").exists()
