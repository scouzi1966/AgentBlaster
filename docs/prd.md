# PRD: AgentBlaster Local Agentic Benchmark Suite

## Summary

Build a cross-platform benchmark suite for local agentic inference engines, starting with AFM MLX, oMLX, Ollama MLX, Rapid-MLX, mlx-lm, vLLM-MLX, and LM Studio. The suite will run standardized OpenAI-compatible and Anthropic-compatible agent workloads, normalize runtime telemetry, and produce reproducible CLI results plus optional professional reports and dashboards.

The product goal is not just to rank engines by tokens/sec. The benchmark must measure whether an engine can sustain real local agent workloads: large repeated system prompts, tool definitions, skills, MCP tools, multi-turn tool loops, streaming, cancellation, structured output, parallel requests, and cache reuse. The strategic goal is to expose where AFM can become the best local AI server for agentic workflows.

## Background

Local agent workflows differ from simple chat benchmarks. Agents repeatedly send large static prefixes: system prompts, tool definitions, skills, repo maps, policy blocks, MCP tool schemas, and recent transcript state. They also create bursts of concurrent requests from subagents, code review loops, search/planning loops, and background automations. This makes time-to-first-token, prefill throughput, prompt-cache hit rate, queueing, and malformed tool-call handling at least as important as decode tokens/sec.

Current local engines expose overlapping but inconsistent APIs and metrics:

- `mlx-lm` exposes an OpenAI-like `/v1/chat/completions` server and standard `usage.prompt_tokens`, `usage.completion_tokens`, and `usage.total_tokens`, but its own docs warn the HTTP server is not production-hardened.
- Ollama exposes OpenAI-compatible APIs and native metrics such as `total_duration`, `load_duration`, `prompt_eval_count`, `prompt_eval_duration`, `eval_count`, and `eval_duration`, with timings in nanoseconds.
- LM Studio exposes OpenAI-compatible, Anthropic-compatible, and native REST APIs. Its native REST responses include enhanced stats such as tokens/sec and TTFT, and its v1 REST API adds model management, stateful chats, authentication, and MCP via API.
- oMLX and Rapid-MLX position themselves around Apple Silicon agent serving, OpenAI-compatible APIs, prompt caching, tool calling, and MLX-native performance.
- vLLM-MLX claims OpenAI and Anthropic APIs, continuous batching, paged KV cache, prefix caching, SSD-tiered cache, and structured output.

The suite should treat OpenAI Chat Completions as the baseline compatibility target, with OpenAI Responses and Anthropic Messages as first-class optional targets because current agents increasingly use those contracts.

## Primary Users

- AFM maintainers optimizing local Apple Silicon agent serving.
- Local AI engine authors comparing runtime behavior under realistic agent stress.
- AI developers choosing an engine for OpenCode, OpenClaw, Hermes Agent, Pi, Cursor, Cline, Aider, Continue, Claude Code-style, and Codex-style local workflows.
- Technical marketers and corporate stakeholders who need defensible charts and reports, not ad hoc terminal screenshots.

## Target Engines

### Phase 1

- AFM MLX: primary engine under development.
- mlx-lm server: baseline MLX reference server.
- LM Studio: mainstream GUI/server local engine with OpenAI, Anthropic, REST API, and MCP support.
- Ollama MLX: mainstream local engine with native and OpenAI-compatible APIs.
- oMLX: MLX-native Apple Silicon server with OpenAI-compatible API, continuous batching, SSD caching, tool calling, JSON schema validation, and MCP tool integration claims.
- Rapid-MLX: MLX-native Apple Silicon server with OpenAI-compatible API, tool parsers, prompt cache, reasoning separation, and agent integration claims.
- vLLM-MLX: optional comparator for OpenAI plus Anthropic server behavior on Apple Silicon.
- Remote OpenAI-compatible providers: any internet-facing endpoint that implements enough of the OpenAI contract, including OpenAI, OpenRouter, Together, Fireworks, Groq, DeepInfra, Cerebras, SambaNova, Anyscale-compatible gateways, LiteLLM gateways, and enterprise/private gateways.
- Remote Anthropic-compatible providers: Anthropic Claude API and any gateway that implements the Anthropic Messages contract.

### Phase 2

- llama.cpp server.
- vLLM, SGLang, TensorRT-LLM, and other x86/Linux engines for cross-platform comparability.
- Additional cloud and hosted baselines, clearly labeled as remote and never mixed with local-engine rankings unless the report explicitly opts in.

## Target Models

### Initial Models

- Qwen3.6-27B dense.
- Gemma 4 31B dense.

### Why These Models

Qwen3.6-27B is an open-weight dense coding and agentic model with long-context positioning. Its Hugging Face model card describes the release as a 27B dense model aimed at coding and real-world agentic workflows, with artifacts compatible with Transformers, vLLM, SGLang, and KTransformers.

Gemma 4 31B is the dense Gemma 4 target. Google describes Gemma 4 models as suitable for reasoning, agentic workflows, coding, and multimodal understanding; the 26B A4B variant is MoE, while 31B is the dense quality target.

### Model Matrix Rules

- Use the same model family and quantization class where possible.
- Track exact model ID, revision, quantization, context length, tokenizer, chat template, and tool parser.
- Never compare different quantizations as if they are equivalent.
- Keep Qwen and Gemma separate in primary charts because chat templates, reasoning conventions, and tool formatting differ.

## Goals

- Provide a standard, reproducible CLI benchmark across engines.
- Support local engines and internet-facing OpenAI-compatible or Anthropic-compatible APIs through the same benchmark runner.
- Normalize OpenAI, Anthropic, and engine-native metrics into one schema.
- Measure agent-relevant runtime behavior: TTFT, prefill throughput, decode throughput, queue latency, cache hit rate, tool-call validity, structured-output validity, and multi-turn success.
- Support both isolated microbenchmarks and end-to-end agent traces.
- Produce professional HTML/PDF/PNG reports suitable for media posts, sales decks, technical blogs, and corporate reviews.
- Make AFM regressions obvious and AFM advantages measurable.

## Non-Goals

- Do not claim a universal model-quality leaderboard from a small synthetic suite.
- Do not require every engine to expose identical proprietary metrics.
- Do not require users to launch engines through the suite; external endpoints must be supported.
- Do not require API keys to be stored in plaintext config files.
- Do not execute arbitrary agent tools against the host without sandboxing and explicit opt-in.
- Do not hide harness failures inside model or engine scores.

## Key Research Findings

OpenAI-compatible APIs are the practical baseline, but not sufficient by themselves. OpenAI distinguishes tool/function calling from structured response formats, and Responses adds stateful multi-turn features such as `previous_response_id` and `max_tool_calls`.

Anthropic prompt caching is directly relevant to local agent benchmarks because it targets repeated static content, long multi-turn conversations, tools, system prompts, and cache breakpoints. Anthropic usage fields also explicitly distinguish normal input tokens, cache creation tokens, cache read tokens, and output tokens.

MCP matters because agents increasingly expose tools through MCP. The current MCP specification defines prompts, resources, and tools as core server primitives; benchmark workloads should include MCP-derived tool catalogs and context growth, not only OpenAI-style inline tools.

Agent frameworks create distinct prompt and tool shapes:

- OpenCode supports many providers and local models through AI SDK/Models.dev, and its tools include file, grep/glob, bash, web, skill, task, and MCP-backed tools.
- OpenClaw local-model docs warn that raw JSON/XML/ReAct text is not a completed tool run and recommend fixing the server chat template/parser before treating text as tool execution. It also supports local OpenAI-compatible backends and leaner local-model modes.
- Hermes Agent includes subagent delegation, code execution, memory, browser, terminal/files, MCP server tools, and exportable trajectories.
- Pi supports local OpenAI-compatible providers, including llama.cpp and MLX launchers, and exposes compatibility toggles for providers that do not support developer role or reasoning effort.

Existing public benchmarks cover pieces of the problem but not the full local-agent runtime problem:

- BFCL covers single-turn, parallel, multiple-candidate, live, and agent function calling.
- tau-bench covers multi-turn tool-agent-user interactions with domain policies.
- StructEval covers structured format generation across many text and visual formats.
- Promptfoo is useful for declarative tests, providers, assertions, concurrency, CLI, and browser views, but a product-grade local-engine benchmark also needs deeper runtime telemetry and standardized engine adapters.

## Benchmark Dimensions

### Protocol Compatibility

- OpenAI Chat Completions: messages, tools, tool_choice, parallel_tool_calls, stream, response_format, seed, usage.
- OpenAI Responses: input items, tools, max_tool_calls, previous_response_id where supported, streaming event shape.
- Anthropic Messages: system, messages, tools, tool use/result blocks, stream, usage, cache_control.
- Engine-native APIs: Ollama native generate/chat metrics, LM Studio `/api/v1` and `/api/v0` stats, AFM metrics, Prometheus endpoints where available.

### Runtime Performance

- Cold start latency.
- Model load time.
- TTFT.
- Prompt/prefill tokens/sec.
- Decode tokens/sec.
- End-to-end latency.
- Queue wait time.
- Request admission behavior under saturation.
- Cancellation latency.
- Error rate.
- Host CPU, RAM, GPU/Metal memory, disk I/O, thermal/power where available.

### Cache And Prefill

- Identical repeated prompt.
- Large static prefix plus small suffix.
- Tool definitions repeated across turns.
- Skills repeated across turns.
- Repo map repeated across turns.
- Tool results inserted after static prefix.
- Cache breakpoints in Anthropic-style requests.
- Prefix cache behavior under concurrent requests.
- Cache invalidation when tool schema, system prompt, or chat template changes.

### Tool Calling

- No tool needed.
- Required tool.
- Named tool.
- Multiple candidate tools.
- Parallel tool calls.
- Nested/dependent tool calls.
- Tool result continuation.
- Malformed tool-call recovery.
- Schema validation and repair.
- Streaming tool-call deltas.
- Tool choice under confusing or adversarial prompts.

### Agentic Workflows

- Code edit loop: inspect files, plan, patch, run tests.
- Search-and-summarize loop: web/search tools, extract, synthesize.
- Repository triage: read issue, inspect code, produce plan.
- Multi-agent fan-out: planner plus N worker requests.
- MCP expansion: many tool schemas and resources injected.
- Skills: markdown skill instructions added to system context.
- Memory/recall: previous sessions and summaries included.
- Long-horizon task: repeated tool calls with policy constraints.

### Structured Output

- JSON mode.
- JSON schema strict output.
- Function/tool argument schema adherence.
- Complex nested schema.
- Enums, arrays, unions, nullable values, additionalProperties.
- Truncation detection.
- Refusal or non-schema output handling.

### Reporting And Observability

- Standardized usage fields.
- Engine-native raw metrics preserved.
- Prometheus scrape support.
- Per-request trace with phases.
- Streaming transcript capture.
- Tool-call transcript capture.
- Reproducibility manifest.
- Failure classification.

## Standard Metric Schema

Every result record should include:

- `run_id`
- `case_id`
- `suite`
- `scenario`
- `engine`
- `engine_version`
- `engine_adapter_version`
- `api_contract`
- `endpoint`
- `model_id`
- `model_revision`
- `model_architecture`
- `quantization`
- `platform`
- `os`
- `cpu`
- `gpu`
- `memory_total_bytes`
- `concurrency`
- `request_started_at`
- `request_completed_at`
- `success`
- `failure_class`
- `failure_detail`
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `cached_input_tokens`
- `cache_write_tokens`
- `cache_hit_ratio`
- `ttft_ms`
- `prompt_eval_ms`
- `decode_ms`
- `total_latency_ms`
- `queue_ms`
- `tokens_per_second_decode`
- `tokens_per_second_prefill`
- `requests_per_second`
- `streaming`
- `tool_calls_requested`
- `tool_calls_emitted`
- `tool_calls_valid`
- `structured_output_valid`
- `finish_reason`
- `raw_usage`
- `raw_stats`
- `raw_response_path`
- `trace_path`

## Metric Normalization

The benchmark must preserve raw metrics and derive normalized metrics separately.

### OpenAI-Like Usage

- `usage.prompt_tokens` maps to `input_tokens`.
- `usage.completion_tokens` maps to `output_tokens`.
- `usage.total_tokens` maps to `total_tokens`.
- `prompt_tokens_details.cached_tokens`, when present, maps to `cached_input_tokens`.

### Anthropic-Like Usage

- `usage.input_tokens` maps to uncached input tokens.
- `usage.cache_read_input_tokens` maps to `cached_input_tokens`.
- `usage.cache_creation_input_tokens` maps to `cache_write_tokens`.
- `usage.output_tokens` maps to `output_tokens`.
- Total input should be reported both excluding and including cache read/write fields.

### Ollama Native Usage

- `prompt_eval_count` maps to `input_tokens`.
- `eval_count` maps to `output_tokens`.
- `prompt_eval_duration` maps to `prompt_eval_ms`.
- `eval_duration` maps to `decode_ms`.
- `load_duration` maps to `load_ms`.
- `total_duration` maps to engine-reported total latency.

### LM Studio Native Stats

- `usage.prompt_tokens`, `usage.completion_tokens`, and `usage.total_tokens` map to standard token fields.
- `stats.time_to_first_token` maps to `ttft_ms`.
- `stats.tokens_per_second` maps to decode throughput unless the API documents otherwise.
- `model_info` and `runtime` are preserved under `raw_stats` and copied into environment metadata when stable.

### Prometheus Metrics

Prometheus metrics should be scraped when an engine exposes `/metrics`. Derived time-series should be stored separately from per-request JSON so reports can show saturation, queue depth, active requests, and memory pressure over time.

## Failure Classification

Every failing test must be classified as one of:

- `engine_protocol_bug`: malformed JSON, malformed SSE, broken endpoint, invalid response envelope, wrong usage field shape.
- `engine_runtime_bug`: crash, timeout, cancellation failure, deadlock, leak, OOM, queue starvation.
- `engine_feature_gap`: endpoint or parameter unsupported.
- `model_quality`: valid response shape but incorrect reasoning, wrong tool, wrong arguments, missing tool, poor policy following.
- `template_or_parser_gap`: model likely can produce the behavior, but the server chat template or parser fails to translate it into API-native shape.
- `harness_bug`: benchmark assertion, adapter, launch, or normalization bug.
- `environmental`: thermal throttling, memory pressure, network/port conflict, missing dependency.

## Product Requirements

### CLI

- `agentblaster engines list`
- `agentblaster engines probe --engine <name> --base-url <url>`
- `agentblaster providers add --name <name> --contract openai|anthropic --base-url <url>`
- `agentblaster providers auth set --provider <name> --api-key-stdin`
- `agentblaster providers auth test --provider <name>`
- `agentblaster run --suite <suite> --engine <engine> --model <model>`
- `agentblaster run --matrix matrix.yaml`
- `agentblaster compare runs/<run-a> runs/<run-b>`
- `agentblaster report runs/<run-id> --format html,pdf,png,json`
- `agentblaster dashboard --runs runs/`
- `agentblaster validate-case path/to/case.yaml`
- `agentblaster export runs/<run-id> --format parquet,jsonl,csv`

### Engine Adapters

- OpenAI-compatible adapter.
- Anthropic-compatible adapter.
- Remote OpenAI-compatible adapter with API-key authentication, custom headers, base URL overrides, and provider-specific capability overrides.
- Remote Anthropic-compatible adapter with API-key authentication, version headers, beta headers, base URL overrides, and provider-specific capability overrides.
- Ollama native adapter.
- LM Studio native REST adapter.
- AFM adapter with AFM-specific metrics and flags.
- mlx-lm adapter.
- oMLX adapter.
- Rapid-MLX adapter.
- Generic HTTP adapter for custom endpoints.

Each adapter must define:

- Supported API contracts.
- Health probe.
- Model list probe.
- Version probe.
- Launch command template, optional.
- Stop command template, optional.
- Request transforms.
- Streaming parser.
- Usage normalizer.
- Native metrics collectors.
- Authentication strategy.
- Secret lookup strategy.
- Known unsupported fields.

### Provider And Secret Management

AgentBlaster must support both local unauthenticated endpoints and internet-facing authenticated providers.

Provider config should include:

- `name`
- `contract`: `openai`, `anthropic`, or `native`
- `base_url`
- `api_key_ref`
- `default_model`
- `headers`
- `capabilities`
- `rate_limits`
- `cost_model`
- `remote`: `true` or `false`

API key storage requirements:

- Required portable paths: environment-variable references for CI, for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`.
- Required portable paths: one-time `--api-key-stdin` entry for scripting without shell history leakage.
- Optional OS-native secure storage: Apple Keychain on macOS.
- Optional OS-native secure storage: Secret Service/libsecret on Linux desktops where available.
- Optional OS-native secure storage: Windows Credential Manager on Windows.
- Support plaintext `.env` only as an explicit opt-in development fallback, with warnings.
- Never write raw API keys to run manifests, traces, logs, reports, or screenshots.
- Redact `Authorization`, `x-api-key`, `api-key`, and provider-specific auth headers in raw artifact capture.

OS keyring feasibility:

- Python can integrate with the `keyring` package, which uses macOS Keychain when available.
- The recommended service name is `AgentBlaster`.
- The recommended username format is `<provider-name>:<credential-name>`, for example `openai:api_key`.
- Keyring support must be optional at install time and fall back cleanly on Linux, Windows, containers, SSH sessions, and headless CI.
- The base package must run on macOS, Linux, and Windows without installing keyring extras.

Remote-provider benchmark rules:

- Remote providers must be labeled `remote` in reports.
- Network latency must be measured separately from model/runtime latency where possible.
- Cost estimates should be optional and based on user-provided or provider-known pricing.
- Rate-limit errors must be classified separately from model or engine failures.
- Remote cloud results must not be used as AFM-vs-local rankings unless explicitly selected.

### Test Case Format

Use declarative YAML or JSON with Pydantic validation:

- `id`
- `title`
- `provenance`
- `suite`
- `api_contract`
- `messages` or `input`
- `tools`
- `mcp_profile`
- `skills`
- `response_format`
- `expected`
- `assertions`
- `metrics`
- `timeout_seconds`
- `tags`
- `risk_level`

Provenance must be explicit:

- `primary_source`
- `public_benchmark_adapted`
- `synthetic_representative`
- `internal_regression`
- `customer_trace_sanitized`

### Suites

#### 1. Protocol Smoke

Purpose: determine whether the engine speaks the claimed API contract.

Cases:

- Basic chat.
- Streaming chat.
- Usage fields present.
- Stop condition.
- Error envelope.
- Model list.
- Tool call simple.
- Structured output simple.

#### 2. Prefill And Cache

Purpose: measure large repeated prompt performance.

Cases:

- 8k, 32k, 128k, and 256k static prefix where supported.
- Same prefix repeated 5 times.
- Same prefix with changing final user turn.
- Same tools plus changing user turn.
- Anthropic-style cache breakpoints where supported.
- Concurrency burst with same prefix.
- Concurrency burst before first cache entry is warm.

Metrics:

- TTFT.
- Prompt eval tokens/sec.
- Cache read/write tokens.
- Cache hit ratio.
- Latency improvement warm vs cold.
- Memory retained by cache.

#### 3. Tool Call Correctness

Purpose: test API-native tool-call shape and argument validity.

Sources:

- BFCL-inspired and sampled cases.
- When2Call-inspired no-call/ask-clarification cases.
- Internal parser regressions.

Cases:

- Single obvious tool.
- Similar tools.
- No tool needed.
- Required tool.
- Named tool.
- Parallel independent tools.
- Dependent nested tools.
- Nullable and union arguments.
- Enum constraints.

#### 4. Structured Output

Purpose: test JSON/schema behavior separately from tool use.

Sources:

- StructEval-inspired JSON/YAML/XML cases.
- JSON Schema stress cases.
- Internal xgrammar/schema regressions.

Cases:

- Flat schema.
- Nested schema.
- Arrays of objects.
- Enum constraints.
- Additional properties false.
- Nullability.
- Truncation-prone schema.
- Invalid user input requiring refusal or explicit error field.

#### 5. Agent Framework Profiles

Purpose: emulate the prompt and tool shape of major local agents.

Profiles:

- OpenCode profile: codebase tools, permissions, grep/glob/read/edit/bash, skills, MCP additions.
- OpenClaw profile: gateway local-model behavior, tools/plugins/skills, lean mode, session/status style.
- Hermes profile: terminal/files, browser, memory, delegation, execute_code, MCP, trajectory export shape.
- Pi profile: minimal coding agent, provider compatibility toggles, local OpenAI endpoint.

Cases should be representative and labeled. Do not present synthetic profiles as official benchmark imports.

#### 6. Multi-Turn Agent Loops

Purpose: measure sustained state, tool result ingestion, and repeated prefill.

Cases:

- Read file then answer.
- Search then summarize.
- Patch then inspect.
- Tool result too large and must be summarized.
- Follow-up uses prior tool result.
- User correction changes plan.
- Policy-constrained support task inspired by tau-bench.

#### 7. Concurrency And Saturation

Purpose: measure how engines behave when multiple agents or subagents run simultaneously.

Concurrency levels:

- 1, 2, 4, 8, 16 by default.
- Higher only when explicitly configured.

Cases:

- Identical prompts.
- Shared prefix different suffix.
- Different prompts same model.
- Mixed short and long requests.
- Streaming all requests.
- Cancellation of one request in a batch.

Metrics:

- Per-request queue wait.
- P50/P95/P99 latency.
- Aggregate throughput.
- Fairness.
- Starvation.
- Error rate.
- Active memory.
- Cache hit rate under parallel load.

#### 8. Reporting And Regression

Purpose: provide stable views for development and public communication.

Reports:

- Executive summary.
- Engine comparison.
- Model comparison.
- Runtime profile.
- Tool-call reliability.
- Structured-output reliability.
- Cache/prefill analysis.
- Concurrency saturation.
- Failure appendix.
- Reproducibility manifest.

## Optional GUI Dashboard

The GUI should be optional and layered on top of the same run database as the CLI.

### Dashboard Capabilities

- Configure engines and endpoints.
- Probe engine capabilities.
- Build benchmark matrices.
- Launch runs.
- Monitor running tests.
- Inspect request traces.
- Compare runs.
- Generate reports.
- Export charts as PNG/SVG.
- Export full reports as HTML/PDF.
- Save presets for AFM release validation, marketing benchmarks, and deep diagnostics.

### Dashboard Views

- Overview: scorecards and warnings.
- Engine Matrix: capabilities and unsupported fields.
- Runtime: TTFT, throughput, queueing, memory, cache.
- Agent Reliability: tool-call and structured-output pass rates.
- Trace Explorer: raw requests/responses, normalized fields, assertions.
- Report Builder: narrative templates and chart selection.

## Architecture

### Recommended Stack

- Python 3.11+ core.
- Typer for CLI.
- Pydantic v2 for schemas.
- httpx/aiohttp for sync and async HTTP.
- FastAPI for optional dashboard API.
- React or plain FastAPI/Jinja dashboard for Phase 1; React only if interactivity becomes valuable enough.
- SQLite for local run metadata.
- DuckDB and Parquet for analytics-scale results.
- JSONL for append-only raw event logs.
- Plotly or Altair for charts.
- Playwright only for dashboard/report visual QA if required.

Python is the right default because the suite needs broad platform support, easy HTTP clients, good data tooling, and simple packaging. Engine launchers can remain shell-command templates per platform.

### Core Components

- `runner`: orchestrates test execution and concurrency.
- `adapters`: per-engine request, launch, probe, and metric code.
- `contracts`: OpenAI, Anthropic, and native response schemas.
- `normalizer`: raw response to canonical metrics.
- `secrets`: API key storage and lookup through OS credential stores, environment variables, and explicit CI configuration.
- `providers`: persisted provider profiles for local and remote endpoints.
- `assertions`: deterministic and LLM-judge assertions.
- `workloads`: YAML/JSON test cases and trace templates.
- `collectors`: process, OS, Prometheus, and native engine telemetry.
- `storage`: run database, raw artifacts, JSONL, Parquet.
- `reporting`: HTML/PDF/PNG and markdown summaries.
- `dashboard`: optional GUI over the same APIs.

### Data Layout

```text
agentbench/
  adapters/
  assertions/
  collectors/
  contracts/
  providers/
  runner/
  secrets/
  reporting/
  suites/
  dashboard/
runs/
  <run-id>/
    manifest.json
    results.jsonl
    metrics.jsonl
    traces/
    raw/
    report.html
    report.pdf
    charts/
```

## Scoring Model

Use separate score families instead of one opaque total score:

- Protocol conformance score.
- Runtime score.
- Prefill/cache score.
- Tool-call score.
- Structured-output score.
- Agent-loop score.
- Concurrency score.
- Observability score.

The public headline should show a radar or scorecard, not one aggregate ranking. Aggregate scores can be computed for internal regression gates but should not hide failure modes.

## Report Quality Requirements

Reports must include:

- Exact engine versions.
- Exact model IDs and revisions.
- Hardware and OS.
- Quantization and context settings.
- Run date.
- Benchmark suite version.
- Unsupported features explicitly called out.
- Confidence notes and sample size.
- Failure taxonomy.
- Raw artifact link/path.

Reports must avoid:

- Comparing engines with different model quantizations without warning.
- Claiming official benchmark scores from adapted or synthetic cases.
- Hiding failed/unsupported cases from denominator math.
- Mixing cold and warm cache results in one metric.

## Enterprise Security Requirements

AgentBlaster must be built with security as a product requirement, not as a later hardening pass. The default posture should be safe for corporate laptops, enterprise CI, private model gateways, and air-gapped or network-restricted environments.

### Security Principles

- Secure by default: risky features are opt-in, visible, and logged.
- Least privilege: benchmark runs should only access the endpoints, files, tools, and network targets explicitly configured for the run.
- Local-first privacy: local benchmark data should remain local unless the user explicitly exports or uploads it.
- No secret leakage: credentials must never appear in logs, traces, reports, screenshots, errors, or generated artifacts.
- Auditability: security-relevant actions must be attributable, timestamped, and reproducible.
- Policy as config: enterprise controls must be enforceable by checked-in policy files and CI flags.
- Separation of duties: report viewers should not need access to raw prompts, raw responses, or secrets.

### Threat Model

AgentBlaster must explicitly defend against:

- API key leakage through logs, traces, report bundles, exception text, screenshots, shell history, and debug output.
- Prompt and response data leakage from corporate documents, source code, customer data, or proprietary benchmark cases.
- Accidental upload of private traces to remote providers.
- Malicious or compromised benchmark cases that request shell, file, browser, network, or MCP tool access.
- Tool poisoning through MCP tool descriptions, skill files, or benchmark-provided tool schemas.
- Prompt injection inside test fixtures, tool results, documents, or fetched web content.
- SSRF-like behavior through benchmark cases that cause requests to private network resources.
- Supply-chain risk from optional agent framework packages, plugins, dashboards, report renderers, and test data.
- Insecure dashboard exposure on shared networks.
- Cross-run contamination through cached prompts, persistent sessions, stored traces, or shared output directories.

### Secrets And Credentials

- API keys should be stored in OS-native credential stores when the optional secret backend is installed and available, with Apple Keychain as the preferred macOS implementation.
- API keys must never be printed, logged, committed, exported in reports, or stored in raw trace artifacts.
- Environment variable and stdin-based secret entry must be supported for CI and headless environments.
- Plaintext secret files are an explicit opt-in fallback only and must trigger a warning.
- Secret values must be redacted before structured logging, exception formatting, trace capture, and report generation.
- Provider auth headers must be redacted by name and by value fingerprint.
- CLI commands that accept secrets must support stdin and must not require putting secrets in argv.
- Run manifests may include secret references, never secret values.
- Secret lookup failures must fail closed and avoid printing nearby environment values.

### Data Protection And Retention

- Raw request and response capture must be configurable per run: `off`, `redacted`, or `full`.
- Default capture mode for remote providers should be `redacted`.
- Default capture mode for local providers can be `redacted` unless the user opts into `full`.
- Reports must support a public-safe mode that excludes raw prompts, raw responses, file paths, usernames, hostnames, local IPs, and environment variables.
- Run artifacts must include a retention policy field.
- A cleanup command must delete raw traces, caches, temporary files, and generated report bundles for a run.
- PII and secret redaction should be regex-based initially, with a pluggable redaction pipeline later.
- Corporate users must be able to run with `--no-raw-traces`.

### Execution Sandbox

- Default suite must not execute host-mutating tools.
- Tool execution tests run in temp sandboxes.
- Shell, file write, browser, and network tools require explicit opt-in.
- File-system tests must use allowlisted working directories.
- Network tests must use allowlisted hosts and ports.
- MCP tests use mock MCP servers by default.
- Third-party Pi/OpenCode/OpenClaw/Hermes packages are never installed automatically.
- Agent framework integration tests must distinguish prompt-shape emulation from executing the real framework.
- Destructive tool fixtures must be disabled unless the user passes a high-friction flag such as `--allow-host-tools`.

### Network Security

- Remote providers must be explicitly configured and labeled.
- The runner must support `--offline` mode that blocks all remote providers and web-dependent tests.
- The runner must support provider allowlists and deny remote fallback by default.
- Corporate proxy configuration must be supported through standard environment variables and explicit provider config.
- TLS verification must be enabled by default.
- Custom CA bundles must be configurable for enterprise gateways.
- Insecure TLS must require explicit opt-in and must be visible in reports.
- Dashboard servers bind to `127.0.0.1` by default.
- Dashboard network binding, auth disablement, and CORS relaxation require explicit flags.

### Policy Controls

AgentBlaster should support a policy file, for example `agentblaster.policy.yaml`, with controls for:

- Allowed providers.
- Allowed API contracts.
- Allowed base URL domains.
- Allowed local ports.
- Allowed file-system roots.
- Allowed network targets.
- Raw trace mode limits.
- Report redaction requirements.
- Dashboard bind policy.
- Secret backend policy.
- Maximum concurrency.
- Maximum prompt tokens.
- Maximum remote spend or request count.
- Whether shell, file write, browser, web, MCP, and third-party framework execution are allowed.

Policy violations must fail closed with a clear error and an audit event.

### Audit Logging

- Security-relevant events must be written to a structured audit log when enabled.
- Events include provider creation, secret reference changes, remote run start, dashboard start, raw trace mode, policy violations, tool execution, MCP server start, and report export.
- Audit logs must redact secrets and sensitive prompt content by default.
- Audit logs should be JSONL for ingestion into corporate logging systems.

### Dashboard Security

- Dashboard is optional and must be disabled by default in CLI-only installs.
- Dashboard binds to localhost by default.
- Remote dashboard access requires explicit bind host and authentication configuration.
- Report downloads must respect redaction mode.
- The dashboard must never expose raw secrets.
- The dashboard should show a visible security posture banner for remote providers, raw traces, insecure TLS, and host-tool execution.

### Supply Chain

- Dependencies should be minimal and pinned in lock files for releases.
- Optional extras must be separated by capability: `secrets`, `dashboard`, `reports`, `dev`.
- Release artifacts should include SBOM generation as a target.
- CI should include dependency vulnerability scanning.
- Benchmark fixtures imported or adapted from public datasets must record provenance and license.
- Third-party plugins or framework packages must never auto-install during a benchmark run.

### Compliance-Oriented Features

- Redacted report mode for external sharing.
- Full internal report mode for private engineering diagnostics.
- Reproducibility manifest without secrets.
- Signed run manifests in later phases.
- Export controls for JSONL, CSV, Parquet, HTML, and PDF with redaction mode recorded.
- Configurable data retention and cleanup.
- Air-gapped local-only operation for local engines and bundled datasets.

## MVP Scope

### MVP Must Have

- CLI runner.
- OpenAI Chat Completions adapter.
- Remote OpenAI-compatible provider support with API key configuration.
- Generic OpenAI-compatible engine profile.
- AFM, mlx-lm, Ollama, LM Studio profiles.
- Basic oMLX and Rapid-MLX profiles as OpenAI-compatible endpoints.
- Probe command.
- Protocol smoke suite.
- Prefill/cache suite.
- Tool-call correctness suite.
- Structured-output suite.
- Concurrency suite.
- Normalized JSONL results.
- HTML report.
- Failure classification.
- Reproducibility manifest.
- Secret redaction for logs, traces, and reports.
- `--no-raw-traces` run mode.
- Localhost-only dashboard default if dashboard is enabled.

### MVP Should Have

- Anthropic Messages adapter.
- Remote Anthropic-compatible provider support with API key configuration.
- Optional OS keyring integration via Python `keyring`, using Apple Keychain on macOS when available.
- LM Studio native stats collector.
- Ollama native stats collector.
- Prometheus collector.
- Agent profile suite for OpenCode, OpenClaw, Hermes, and Pi.
- Report PNG exports.
- DuckDB/Parquet export.
- `agentblaster.policy.yaml` enforcement for provider allowlists, raw trace mode, dashboard binding, and host-tool execution.
- Structured security audit log.

### MVP Could Have

- FastAPI dashboard.
- PDF export.
- MCP mock server suite.
- LLM-as-judge failure summaries.
- Public static leaderboard generator.
- Provider cost estimation for remote API runs.
- SBOM generation and dependency vulnerability scan target.

## Phase Plan

### Phase 0: Requirements And Harness Spike

- Finalize canonical result schema.
- Implement basic OpenAI-compatible adapter.
- Run AFM vs mlx-lm on smoke and prefill cases.
- Produce a minimal HTML report.

Exit criteria:

- One command runs a small matrix and writes reproducible artifacts.
- Raw and normalized metrics are both visible.

### Phase 1: MVP CLI Benchmark

- Add engine profiles for AFM, mlx-lm, LM Studio, Ollama, oMLX, Rapid-MLX.
- Add tool-call, structured-output, prefill/cache, and concurrency suites.
- Add failure classification.
- Add report builder.
- Add baseline enterprise controls: secret redaction, no-raw-traces mode, local-only mode, provider allowlists, and localhost-only dashboard defaults.

Exit criteria:

- Can compare target engines on Qwen3.6-27B and Gemma 4 31B where supported.
- Can show cold vs warm prefill, serial vs concurrent, and tool-call validity.

### Phase 2: Agent Profiles And Native Metrics

- Add OpenCode, OpenClaw, Hermes, and Pi profiles.
- Add Anthropic Messages adapter.
- Add Ollama native and LM Studio native stats collection.
- Add Prometheus scraping.
- Add MCP mock server workloads.
- Add structured audit logs and policy-file enforcement for host tools, network targets, raw traces, and remote providers.

Exit criteria:

- Can show why an engine succeeds or fails under realistic local agent prompts.
- Can separate engine bugs, model quality, parser/template gaps, and harness bugs.

### Phase 3: Dashboard And Publication Reports

- Add optional FastAPI dashboard.
- Add run builder.
- Add chart export.
- Add PDF report export.
- Add static report bundles.
- Add dashboard authentication options, redacted report downloads, and security posture indicators.

Exit criteria:

- User can configure, run, inspect, compare, and export reports without editing YAML.

### Phase 4: Public Benchmark Track

- Add public benchmark adapters and carefully labeled sampled subsets.
- Add cloud reference baselines.
- Add signed run manifests.
- Add reproducibility verifier.
- Add SBOM/release provenance artifacts and optional signed report bundles.

Exit criteria:

- Reports are credible for external posts and corporate comparisons.

## Open Questions

- Should the benchmark suite live inside AFM initially or become a standalone repo from day one?
- Should Promptfoo remain part of the implementation or only a source of compatible suite ideas?
- Which exact Qwen3.6-27B and Gemma 4 31B MLX quantizations should be canonical?
- Which hardware tiers should be official: M2/M3/M4/M5, 32 GB/64 GB/128 GB, plus x86 Linux GPU?
- Should GUI reports prioritize static publication quality or interactive engineering diagnostics first?
- Should public comparisons include cloud models, or keep cloud baselines separate to avoid confusing local-vs-remote claims?
- Which OS keyring backends should be tested in CI or manual release checks beyond macOS Keychain?
- Which hosted OpenAI-compatible providers should ship as first-party presets versus user-defined provider profiles?
- What enterprise policy schema should be stable for v1: simple YAML, OPA/Rego integration, or both?
- Which redaction patterns should be built in for source code, customer data, and common API-key formats?
- Should dashboard authentication be local password, token file, reverse-proxy only, or all of these?

## Success Metrics

- AFM releases can run the benchmark as a regression gate.
- Reports clearly show AFM strengths and weaknesses versus oMLX, Rapid-MLX, Ollama MLX, mlx-lm, and LM Studio.
- The benchmark catches prefill/cache regressions that simple tokens/sec tests miss.
- The benchmark catches malformed streaming/tool-call regressions.
- The suite can generate a credible public report in under 10 minutes after a run completes.
- New engine adapters can be added without changing core runner code.

## Source Notes

- OpenAI Structured Outputs distinguish function calling from structured response formats: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI Responses includes multi-turn `previous_response_id` and `max_tool_calls`: https://platform.openai.com/docs/api-reference/responses/object
- Anthropic prompt caching targets repeated prefixes, long context, tools, system prompts, and multi-turn conversations: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- MCP server primitives are prompts, resources, and tools: https://modelcontextprotocol.io/specification/2025-11-25/server/index
- Ollama native API usage metrics include prompt/decode counts and durations: https://docs.ollama.com/api/usage
- Ollama OpenAI compatibility includes Responses API support with limitations: https://docs.ollama.com/api/openai-compatibility
- LM Studio supports OpenAI-compatible, Anthropic-compatible, and native REST APIs: https://lmstudio.ai/docs/developer/rest
- LM Studio native REST includes TTFT and tokens/sec stats: https://lmstudio.ai/docs/developer/rest/endpoints
- mlx-lm HTTP server is OpenAI-like and reports standard usage fields: https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md
- oMLX documents OpenAI-compatible serving plus tool calling and structured output claims: https://github.com/jundot/omlx
- Rapid-MLX documents OpenAI-compatible serving, tool calling, prompt cache, and agent setup claims: https://github.com/raullenchai/Rapid-MLX
- vLLM-MLX documents OpenAI and Anthropic APIs, continuous batching, paged KV cache, prefix caching, and structured output: https://github.com/waybarrios/vllm-mlx
- OpenCode provider docs describe local model support through AI SDK/Models.dev: https://opencode.ai/docs/providers/
- OpenCode tools/permissions docs define built-in tools and MCP-style permission gating: https://dev.opencode.ai/docs/tools/
- OpenClaw local model docs describe OpenAI-compatible local endpoints and tool-call parser/template failure modes: https://docs.openclaw.ai/gateway/local-models
- OpenClaw tools docs describe tools, skills, plugins, and structured function definitions: https://docs.openclaw.ai/tools/index
- Hermes Agent docs describe multi-platform agents, delegation, execute_code, skills, MCP, and trajectories: https://hermes-agent.nousresearch.com/docs/
- Pi local agent docs describe OpenAI-compatible local model configuration: https://huggingface.co/docs/hub/agents-local
- Qwen3.6-27B model card: https://huggingface.co/Qwen/Qwen3.6-27B
- Gemma 4 31B model card: https://huggingface.co/google/gemma-4-31B
- BFCL technical report: https://www2.eecs.berkeley.edu/Pubs/TechRpts/2025/EECS-2025-184.html
- tau-bench paper page: https://huggingface.co/papers/2406.12045
- StructEval project: https://structeval.github.io/
- Promptfoo docs: https://www.promptfoo.dev/docs/intro/
