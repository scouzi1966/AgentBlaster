# Representative Local-Agent Profiles

AgentBlaster includes deterministic profile generators for common local-agent workflow shapes. These profiles are synthetic representative workloads, not exact copies of upstream agent internals.

## Profiles

- `opencode`: repository triage, file reads, shell/test loop replay, and skill-driven coding workflow pressure.
- `openclaw`: strict API-native tool envelopes, local tool-parser behavior, and structured-output compatibility.
- `hermes`: Nous Hermes-style planner and multi-tool workflows, browser fixture, MCP fixture expansion, LCP context-bundle boundaries, and memory-like context.
- `pi`: lean local-provider compatibility with simple chat, trace replay, and structured summary behavior.
- `aider`: patch-oriented pair-programming loop with file context, diff reasoning, and replayed tests.
- `cline`: plan/action workflow with bounded fixture actions, file inspection, and shell replay.
- `continue`: IDE-local retrieval pattern with deterministic documentation lookup and structured engineering summary.
- `codex`: sandbox-aware command planning with deterministic shell replay and concise final status.

## Commands

List profiles:

```bash
agentblaster agents profiles
```

Generate a suite for all profiles:

```bash
agentblaster agents suite --profile all --output examples/suites/agentic-local-profiles.yaml
agentblaster validate-case examples/suites/agentic-local-profiles.yaml
```

Generate one profile suite:

```bash
agentblaster agents suite --profile opencode --output examples/suites/agentic-opencode.yaml
```

Generated suites use existing AgentBlaster primitives: simulated tools, MCP fixture profiles with deterministic fixture results, LCP context bundles, skill packs, structured-output assertions, trace replay, and provenance/risk metadata. Generation does not call providers, install third-party agent frameworks, or touch host tools.
