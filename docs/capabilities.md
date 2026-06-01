# AgentBlaster Capability Preflight

Capability preflight checks whether a configured provider declares support for the features required by a suite before a benchmark run starts.

This is intentionally separate from policy enforcement. Policy answers "is this run allowed?" Capability preflight answers "is this provider likely to exercise this suite fairly?"

## Commands

Inspect suite requirements:

```bash
agentblaster suite-requirements --suite trace-replay
```

Check a provider against a suite:

```bash
agentblaster providers check-suite --provider afm --suite toolcall
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
- `structured_output`: response-format or expected JSON field support.
- `tool_calling`: API-native function/tool-call envelope support.
- `trace_replay`: multi-turn message replay with assistant/tool turns.
- `skills`: large system-prompt skill-prefix injection.
- `responses_api`: OpenAI Responses-style stateful response input support.

## Provider Declarations

Provider profiles can include a `capabilities` object. Presets for internet-facing OpenAI and Anthropic endpoints declare their core features. Local presets are intentionally conservative where engine support varies by version or launch flags.

Declare local-engine capabilities with the CLI:

```bash
agentblaster providers capabilities list --provider afm
agentblaster providers capabilities enable --provider afm --capability tool_calling
agentblaster providers capabilities enable --provider afm --capability streaming
agentblaster providers capabilities disable --provider afm --capability structured_output
agentblaster providers capabilities clear --provider afm --capability structured_output
```

Use `enable` when a provider supports a feature, `disable` when a provider is known not to support a feature, and `clear` when support should return to unknown.

Unknown local capabilities should be resolved by probing, documentation, or a small smoke run before promoting a suite to a release gate.
