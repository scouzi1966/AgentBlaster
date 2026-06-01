# AgentBlaster Capability Preflight

Capability preflight checks whether a configured provider declares support for the features required by a suite before a benchmark run starts.

This is intentionally separate from policy enforcement. Policy answers "is this run allowed?" Capability preflight answers "is this provider likely to exercise this suite fairly?"

## Commands

Inspect suite requirements:

```bash
agentblaster suite-requirements --suite trace-replay
agentblaster suite-requirements --suite agentic-tool-loop
agentblaster suite-requirements --suite agent-fanout
agentblaster suite-requirements --suite cancellation
agentblaster suite-requirements --suite-file examples/suites/harness-judge-rubric.yaml
```

Check a provider against a suite:

```bash
agentblaster providers check-suite --provider afm --suite toolcall
agentblaster providers check-suite --provider afm --suite agentic-tool-loop --strict-unknown
agentblaster providers check-suite --provider openai --suite trace-replay --output-json reports/openai-trace-preflight.json
```

Fail on unknown capabilities for release gates:

```bash
agentblaster providers check-suite --provider afm --suite toolcall --strict-unknown
```

Run execution performs capability preflight by default:

```bash
agentblaster run --suite toolcall --engine afm --model mlx-community/Qwen3.6-27B
agentblaster run --suite toolcall --engine afm --model mlx-community/Qwen3.6-27B --strict-unknown-capabilities
```

Disable execution preflight only for exploratory work where you intentionally want to observe the provider failure shape:

```bash
agentblaster run --suite toolcall --engine afm --model mlx-community/Qwen3.6-27B --no-capability-preflight
```

## Capability States

- `supported`: the provider declares support, or AgentBlaster can infer support from the adapter contract.
- `missing`: the provider or adapter explicitly does not support the feature.
- `unknown`: the provider does not declare the feature. This does not fail by default because local OpenAI-compatible engines often do not advertise capabilities consistently.

During `agentblaster run`, `missing` capabilities fail before any provider request is sent. `unknown` capabilities are allowed by default and fail only with `--strict-unknown-capabilities`.

## Detected Suite Requirements

- `chat`: basic chat request/response support.
- `streaming`: streaming/SSE response support.
- `cancellation`: request cancellation, stream abort, or equivalent provider-side stop behavior.
- `structured_output`: response-format or expected JSON field support.
- `judge_rubric`: deterministic structured model-judge rubric verdict support for judge-rubric harness cases.
- `tool_calling`: API-native function/tool-call envelope support.
- `tool_loop`: bounded deterministic tool-result round trip support for cases with `max_tool_calls > 1`.
- `mcp_profile`: deterministic MCP fixture tool-catalog injection.
- `trace_replay`: multi-turn message replay with assistant/tool turns.
- `skills`: large system-prompt skill-prefix injection.
- `lcp_context`: deterministic LCP-style local context fixture injection.
- `responses_api`: OpenAI Responses-style stateful response input support.
- `prompt_caching`: provider-recognized prompt/cache-control metadata support.

## Provider Declarations

Provider profiles can include a `capabilities` object. Presets for internet-facing OpenAI and Anthropic endpoints declare their core features. Local presets declare the conservative contract surfaces needed for campaign preflight, while fragile or version-dependent surfaces such as prompt caching remain undeclared until verified for that engine build and launch mode.

Declare local-engine capabilities with the CLI:

```bash
agentblaster providers capabilities list --provider afm
agentblaster providers capabilities enable --provider afm --capability tool_calling
agentblaster providers capabilities enable --provider afm --capability streaming
agentblaster providers capabilities enable --provider afm --capability cancellation
agentblaster providers capabilities disable --provider afm --capability structured_output
agentblaster providers capabilities clear --provider afm --capability structured_output
```

Use `enable` when a provider supports a feature, `disable` when a provider is known not to support a feature, and `clear` when support should return to unknown.

Unknown local capabilities should be resolved by probing, documentation, or a small smoke run before promoting a suite to a release gate.

Anthropic Messages-compatible providers are intentionally conservative for OpenAI-style structured-output cases. AgentBlaster does not treat Anthropic Messages as native `response_format` support unless `structured_output` is explicitly declared on that provider. This makes generated `judge-rubric` suites fail preflight for Anthropic-compatible local endpoints until the operator has verified an equivalent JSON/schema mode or accepted prompt-only JSON discipline.

Prompt caching is inferred only for remote Anthropic providers. Local Anthropic-compatible presets such as `lm-studio-anthropic` and `vllm-mlx-anthropic` report `prompt_caching` as unknown until declared, because local servers may accept Anthropic-style request envelopes while ignoring cache-control metadata.

Dry-run plans also include per-case `surfaces=` fields so generated harness suites expose cases such as `structured_output,judge_rubric`, `prompt_caching`, `tool_loop`, or `cancellation` before dispatch.

`mcp_profile` is reported separately from `tool_calling` so reviewers can see that a suite injects deterministic MCP-style fixture catalogs. Provider compatibility still depends on API-native tool/function-call support because AgentBlaster translates fixture MCP profiles into provider tool schemas before dispatch. If the provider emits one of those fixture MCP tool calls, AgentBlaster can evaluate deterministic fixture results without contacting a live MCP server.

`tool_loop` is reported separately from `responses_api`. AgentBlaster can run bounded deterministic tool-result round trips over contracts that support trace-style message replay. OpenAI Responses stateful continuation still uses the separate `responses_api` requirement when `previous_response_id` is declared.

The built-in `agentic-tool-loop` suite requires `tool_calling`, `tool_loop`, `mcp_profile`, and `lcp_context`. Its cases cover successful deterministic tool-result replay, MCP fixture resource calls under an attached LCP context, and an intentional max-tool-call boundary case for stop-reason reporting.

Generated `judge-rubric` suites require both `structured_output` and `judge_rubric`. The `judge_rubric` requirement is derived from the `judge-rubric`/`model-judge` tags or the `judge_verdict_valid` metric, and compatibility follows the provider's structured-output declaration.
