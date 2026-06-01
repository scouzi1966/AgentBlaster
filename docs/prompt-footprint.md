# Prompt Footprint Analysis

AgentBlaster can analyze suite prompt footprint before provider dispatch. This is useful for local-agent benchmarks because repeated system prompts, tool schemas, MCP catalogs, skills, and trace replay messages drive prefill cost and cache behavior.

## Command

```bash
agentblaster suite-footprint --suite trace-replay --output-json reports/trace-replay-footprint.json
agentblaster suite-footprint --suite-file examples/suites/agentic-local-profiles.yaml --output-json reports/agentic-local-profiles-footprint.json
```

The report breaks estimated prompt tokens into:

- `system_prompt`
- `prompt`
- `messages`
- `tools`
- `simulated_tools`
- `mcp_profile`
- `skills`

It also reports static-prefix fingerprints shared across cases. Shared prefixes are relevant for prompt-cache and prefill diagnostics because agents often repeat the same policy blocks, tool catalogs, and skill instructions across many turns.

## Interpretation

Token estimates use a deterministic character-count heuristic for planning. They are not billing records and should not be used as provider invoices. Use the report to identify suites that need prefill stress, cache diagnostics, or tighter policy ceilings before execution.
