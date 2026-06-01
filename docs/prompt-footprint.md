# Prompt Footprint Analysis

AgentBlaster can analyze suite prompt footprint before provider dispatch. This is useful for local-agent benchmarks because repeated system prompts, tool schemas, MCP catalogs, LCP context bundles, skills, and trace replay messages drive prefill cost and cache behavior.

## Command

```bash
agentblaster suite-footprint --suite trace-replay --output-json reports/trace-replay-footprint.json
agentblaster suite-footprint --suite-file examples/suites/agentic-local-profiles.yaml --output-json reports/agentic-local-profiles-footprint.json
agentblaster matrix pressure-audit examples/matrices/qwen-gemma-stress.yaml --output-json reports/qwen-gemma-stress-pressure.json
```

The report breaks estimated prompt tokens into:

- `system_prompt`
- `prompt`
- `messages`
- `tools`
- `simulated_tools`
- `mcp_profile`
- `lcp_profile`
- `skills`

It also reports static-prefix fingerprints shared across cases and `potential_cache_reuse_tokens`, the duplicated static-prefix estimate after the first case in each shared-prefix group. Shared prefixes are relevant for prompt-cache and prefill diagnostics because agents often repeat the same policy blocks, tool catalogs, LCP context bundles, and skill instructions across many turns.

## Matrix Pressure Audits

`agentblaster matrix pressure-audit` lifts suite footprint analysis to a whole matrix. It reports:

- Run, engine, model, suite, and concurrency inventory.
- Scheduled prompt tokens across all cases.
- Concurrent-window prompt tokens for the largest prompts likely to be in flight together.
- Static-prefix tokens versus dynamic prompt/message tokens.
- Output token budget.
- Shared static-prefix groups, repeated static-prefix token pressure, and potential cache-reuse tokens.
- Concurrency-weighted pressure score for comparing stress plans.
- Highest-pressure matrix entries before dispatch.

Use this before expensive Qwen/Gemma stress campaigns to decide whether a matrix is mostly testing protocol correctness, prompt-cache/prefill behavior, decode throughput, or scheduler/concurrency pressure.

## Interpretation

Token estimates use a deterministic character-count heuristic for planning. They are not billing records and should not be used as provider invoices. Use the report to identify suites that need prefill stress, cache diagnostics, or tighter policy ceilings before execution.
