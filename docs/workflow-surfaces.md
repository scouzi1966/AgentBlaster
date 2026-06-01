# AgentBlaster Workflow Surface Catalog

AgentBlaster treats agentic workflow support as explicit benchmark input surfaces. This keeps engine scoring separate from app self-tests while making protocol coverage auditable across local and remote providers.

## Surfaces

- `openai-anthropic-tool-calling`: OpenAI-compatible and Anthropic-compatible tool declarations, tool-call envelopes, argument JSON, and deterministic tool-result replay.
- `mcp-fixtures`: static MCP-style tool, resource, and prompt fixtures, including wide tool catalogs for prefill pressure.
- `skill-packs`: deterministic skill preambles for local-agent workflow pressure, large repeated system prompts, and instruction retention.
- `lcp-emerging`: fixture-only local context protocol style workflows: scoped context bundles, session memory, retrieval attachments, and redacted context metadata.
- `harness-engineering`: generated benchmark-method workloads such as prefill, concurrency, contract fuzzing, metamorphic variants, and cache replay.

## Commands

```bash
agentblaster catalog workflow-surfaces
agentblaster catalog workflow-surfaces --format json --output reports/workflow-surfaces.json
agentblaster catalog workflow-surfaces --format markdown --output reports/workflow-surfaces.md
agentblaster catalog lcp-profiles --output-json reports/lcp-profiles.json
```

## Security Posture

The catalog is static and deterministic. It does not launch host MCP servers, execute host tools, attach real local context providers, call browsers, read user files, or contact remote APIs. LCP coverage is fixture-only until contracts stabilize and enterprise policy can require explicit opt-in for real context providers.

## Intended Use

Use the catalog to answer these release and benchmark-design questions:

- Which workflow families are covered by a benchmark suite or release candidate?
- Which surfaces are stable fixtures versus emerging or experimental research surfaces?
- Which surfaces impose large prompt/prefix pressure and should be correlated with TTFT, prefill throughput, cached input tokens, and cache hit ratios?
- Which surfaces require enterprise policy allowlists before provider dispatch?
- Which future surfaces need fixture coverage before they become scoring dimensions?
