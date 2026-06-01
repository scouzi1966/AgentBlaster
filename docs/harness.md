# Harness Engineering Suites

AgentBlaster can generate deterministic benchmark suites that stress emerging agentic harness techniques without calling providers during generation.

The built-in `harness-engineering` suite provides a stable first-class workload for emerging harness-method coverage in ordinary matrices and dashboard launches. It covers streaming contract fuzzing, metamorphic prompt-invariance, static-prefix cache replay with prompt-caching preflight, and deterministic judge-rubric JSON discipline. The built-in `tool-parser-repair` suite isolates local-model parser failures where engines emit raw JSON, XML, markdown, or ReAct-style text instead of API-native tool calls. Generated harness suites remain available when operators need larger or seeded variants for research campaigns, including mixed MCP/LCP/skills/tool-loop stacks.

## Profiles

- `prefill`: expands source cases with large deterministic system prefixes to expose prefill, cache reuse, and repeated prompt costs.
- `concurrency`: clones source cases into burst workloads to expose queueing, rate limiting, scheduling, and isolation behavior.
- `cancellation`: converts source cases into streaming abort workloads with deterministic `cancel_after_ms` timings.
- `contract-fuzz`: creates streaming, structured-output, and tool-call protocol edge cases for OpenAI-compatible and Anthropic-compatible endpoints.
- `tool-parser-repair`: creates required-tool cases that reject raw JSON, XML, markdown, or ReAct text as completed tool calls.
- `metamorphic`: creates equivalent wording and wrapper variants that preserve source assertions while testing whether agent behavior is stable under harmless prompt changes.
- `cache-replay`: creates warmup, identical replay, suffix mutation, and static-prefix invalidation variants for prompt-cache diagnostics.
- `orchestration`: creates multi-tool routing cases with distractor tools to stress planning, tool choice, argument validity, deterministic tool-result round trips, and tool-loop limits.
- `skills`: creates static skill-catalog prefixes with explicit skill metadata and skill-selection metrics.
- `emerging-workflows`: combines MCP fixture catalogs, LCP context bundles, skill prefixes, simulated tools, tool-loop routing, cache controls, and prefill metrics in one local-agent workflow stack.
- `judge-rubric`: creates deterministic structured-output evaluator cases to test model-judge rubric discipline without invoking an external judge service.

Cancellation workloads can be represented by cases with `cancel_after_ms`. Dry-run plans and capability preflight expose the cancellation requirement before execution so provider adapters can be calibrated without silently treating cancellation as an ordinary long-running completion. The `cancellation` harness profile generates streaming cancellation cases with increasing abort timings and normalized `canceled` plus `cancellation_latency_ms` metrics.

Tool-loop workloads are represented by cases with `max_tool_calls > 1`. The runner sends provider-emitted deterministic fixture tool results back as trace messages, then asks for a final answer within the declared bound. This covers built-in simulated tools, deterministic MCP fixture tools, and AgentBlaster-owned orchestration fixture tools such as `route_agentblaster_task`. It exercises agent planning and tool-result integration without live host tools, live MCP servers, or network access.

Tool-parser repair workloads are represented by required-tool cases with `tool_parser_repair_required`, `tool_calls_valid`, and `invalid_tool_call_count` metrics. They are intended for OpenClaw-style and other local-agent compatibility testing where a model may emit plausible raw JSON, XML, or ReAct text that the server must not count as a completed tool call. Capability preflight reports both `tool_calling` and `tool_parser_repair`: generic tool support is a transport requirement, while parser-repair support is strict behavior and remains `unknown` unless the provider profile declares it explicitly.

Judge-rubric workloads are represented by structured-output cases tagged `judge-rubric` and `model-judge`, with `judge_verdict_valid` in the normalized metrics. Capability preflight reports both `structured_output` and `judge_rubric`; Anthropic-compatible local endpoints must explicitly declare `structured_output` before these generated suites are considered compatible.

## Provenance

Generated suites include suite-level provenance:

- `origin`: `harness_generated`
- `source_suite`: source suite name
- `generator`: `agentblaster.harness`
- `generator_profile`: selected profile
- `generator_seed`: deterministic generation seed
- `generator_repeats`: repeat count
- `risk_labels`: includes `synthetic` and `harness-generated`

The provenance is written into generated YAML, the run `suite.json` snapshot, the run manifest, and report metadata. Public reports should cite the suite SHA-256 and provenance summary so readers can distinguish engine behavior from workload-generation choices.

## Commands

```bash
agentblaster harness profiles
agentblaster harness generate --profile contract-fuzz --suite smoke --repeats 1 --seed 0 --output examples/suites/harness-contract-fuzz.yaml
agentblaster harness generate --profile tool-parser-repair --suite smoke --repeats 2 --seed 41 --output examples/suites/harness-tool-parser-repair.yaml
agentblaster harness generate --profile metamorphic --suite smoke --repeats 3 --seed 13 --output examples/suites/harness-metamorphic.yaml
agentblaster harness generate --profile cache-replay --suite cache-control --repeats 2 --seed 17 --output examples/suites/harness-cache-replay.yaml
agentblaster harness generate --profile cancellation --suite smoke --repeats 3 --seed 23 --output examples/suites/harness-cancellation.yaml
agentblaster harness generate --profile orchestration --suite smoke --repeats 3 --seed 29 --output examples/suites/harness-orchestration.yaml
agentblaster harness generate --profile skills --suite smoke --repeats 2 --seed 37 --output examples/suites/harness-skills.yaml
agentblaster harness generate --profile emerging-workflows --suite smoke --repeats 2 --seed 37 --output examples/suites/harness-emerging-workflows.yaml
agentblaster harness generate --profile judge-rubric --suite smoke --repeats 2 --seed 31 --output examples/suites/harness-judge-rubric.yaml
agentblaster harness review --suite-file examples/suites/harness-contract-fuzz.yaml --output-json reports/harness-contract-fuzz-review.json
agentblaster validate-case examples/suites/harness-contract-fuzz.yaml
agentblaster run --suite-file examples/suites/harness-contract-fuzz.yaml --engine afm --model mlx-community/Qwen3.6-27B --dry-run
```

`agentblaster harness review` writes `agentblaster.harness-review.v1`, a static, publication-safe JSON artifact that summarizes generated-suite provenance, capability surfaces, multi-tool catalog cases, tool-loop cases, assertion types, metrics, tags, risk signals, and calibration requirements. It excludes prompts, messages, raw provider payloads, API keys, request headers, and keyring values.

Release qualification, claim readiness, and dashboard review indexes preserve only compact harness-review summaries: suite name, case count, generated status, generator profile, review status, calibration requirement, selected surface counts, and assertion counts.

## Agent Profile Suites

Representative local-agent workflow suites are generated separately with `agentblaster agents suite --profile all --output examples/suites/agentic-local-profiles.yaml`. See `docs/agent-profiles.md` for OpenCode, OpenClaw, Nous Hermes with MCP/LCP context boundaries, and Pi profile details.

Use the generated `skills` harness when you need to isolate skill-prefix overhead from broader agent profiles. It preserves source-case assertions while adding deterministic skill catalogs, `skills` metadata, prefill/cache metrics, and `skill_selection_valid` scoring hooks for local-agent workflow comparisons.
