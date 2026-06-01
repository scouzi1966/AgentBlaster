from __future__ import annotations

import httpx
import json

from agentblaster.adapters import AnthropicCompatibleAdapter
from agentblaster.capabilities import check_suite_compatibility, suite_requirements
from agentblaster.models import ApiContract, BenchmarkCase, ProviderConfig
from agentblaster.prompt_footprint import suite_prompt_footprint
from agentblaster.suites import BUILTIN_SUITES


def test_cache_control_suite_is_builtin_and_requires_prompt_caching() -> None:
    suite = BUILTIN_SUITES["cache-control"]
    requirements = {requirement.key for requirement in suite_requirements(suite)}

    assert "prompt_caching" in requirements
    assert "cache-control" in suite.cases[0].tags
    report = check_suite_compatibility(
        ProviderConfig(name="anthropic", contract=ApiContract.ANTHROPIC, base_url="https://example.com/v1", remote=True),
        suite,
        strict_unknown=True,
    )
    assert report.compatible is True


def test_anthropic_adapter_serializes_cache_control_on_system_prefix() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "agentblaster-ok"}], "usage": {"input_tokens": 3, "output_tokens": 1}},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(name="anthropic", contract=ApiContract.ANTHROPIC, base_url="https://example.com/v1")
    adapter = AnthropicCompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="cachecase",
        title="cache case",
        system_prompt="Static cacheable system prefix.",
        cache_control={"type": "ephemeral"},
        prompt="Reply with exactly: agentblaster-ok",
        expected_substring="agentblaster-ok",
    )

    response = adapter.chat_completion("claude-test", case)

    assert response.text == "agentblaster-ok"
    assert captured["system"] == [
        {"type": "text", "text": "Static cacheable system prefix.", "cache_control": {"type": "ephemeral"}}
    ]


def test_anthropic_adapter_serializes_cache_control_on_tool_catalog_boundary() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "agentblaster-ok"}], "usage": {"input_tokens": 3, "output_tokens": 1}},
            headers={"content-type": "application/json"},
        )

    provider = ProviderConfig(name="anthropic", contract=ApiContract.ANTHROPIC, base_url="https://example.com/v1")
    adapter = AnthropicCompatibleAdapter(provider, client=httpx.Client(transport=httpx.MockTransport(handler)))
    case = BenchmarkCase(
        id="cachetools",
        title="cache tools",
        cache_control={"type": "ephemeral"},
        prompt="Reply with exactly: agentblaster-ok",
        expected_substring="agentblaster-ok",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup_fixture",
                    "description": "Lookup a deterministic fixture.",
                    "parameters": {"type": "object", "properties": {"key": {"type": "string"}}},
                },
            }
        ],
    )

    response = adapter.chat_completion("claude-test", case)

    assert response.text == "agentblaster-ok"
    assert captured["tools"][0]["name"] == "lookup_fixture"
    assert captured["tools"][0]["cache_control"] == {"type": "ephemeral"}


def test_prompt_footprint_accounts_for_cache_control_component() -> None:
    suite = BUILTIN_SUITES["cache-control"]
    report = suite_prompt_footprint(suite)

    assert report["component_totals"]["cache_control"] > 0
    assert any("cache-control" in case["surfaces"] for case in report["cases"])
