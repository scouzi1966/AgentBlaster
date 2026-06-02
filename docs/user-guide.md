# AgentBlaster User Guide

This guide explains how to configure, run, inspect, and publish AgentBlaster benchmark results. It is intentionally practical: start with a provider, run a small suite, expand to a matrix, then generate release-quality evidence.

Command names and flags may evolve. When a command fails because a flag changed, run the matching `--help` command first and keep the same workflow intent.

## 1. What AgentBlaster tests

AgentBlaster is built for agentic workloads, not only single-turn chat throughput. It focuses on the failure modes that matter when local or remote models are used as coding agents, tool-using assistants, automation workers, or workflow coordinators.

| Surface | What is measured |
| --- | --- |
| OpenAI-compatible APIs | Chat completions, responses-style payloads where supported, streaming behavior, usage fields, tool calls, structured output, and error handling. |
| Anthropic-compatible APIs | Message contracts, tool-use blocks, streaming events, stop reasons, and token accounting where available. |
| Local MLX engines | AFM, oMLX, Ollama MLX, Rapid MLX, LM Studio, and similar local endpoints. |
| Remote engines | Internet-facing OpenAI-compatible and Anthropic-compatible services using API keys. |
| Agentic workflows | Tool calling, MCP-style tools, long system prompts, repeated prefill pressure, concurrency, cancellation, fanout, recovery, trace replay, and harness engineering. |
| Reporting | Normalized telemetry, evidence bundles, release gates, publication bundles, and corporate-friendly scorecards. |

AgentBlaster treats provider-reported statistics as input evidence, not as truth. Wall-clock measurements, normalized metrics, trace metadata, and provider usage fields should be recorded separately so engines with different reporting formats can still be compared fairly.

## 2. Core concepts

| Concept | Meaning |
| --- | --- |
| Provider | A named API endpoint plus contract type, authentication method, default model, capability declarations, and security policy. |
| Engine | The implementation behind a provider, such as AFM, LM Studio, Ollama, or a hosted API gateway. |
| Suite | A grouped set of benchmark cases for one behavior area, such as smoke, tool calls, structured output, concurrency, or cache control. |
| Case | A single test scenario with prompts, expected behavior, scoring rules, metadata, and optional tools. |
| Run | One execution of a suite or matrix against a provider and model. |
| Matrix | A planned set of runs across providers, models, suites, concurrency levels, or other variables. |
| Artifact | A generated JSON, HTML, Markdown, PDF, bundle, or trace file that records benchmark evidence. |
| Gate | A policy check that converts benchmark evidence into pass, fail, or warning decisions. |
| Redaction | Removal or minimization of secrets, raw prompts, raw completions, headers, keys, and sensitive metadata. |

## 3. Installation

Use a Python virtual environment. Python keeps the suite portable across macOS, Linux, and Windows while still allowing optional macOS Keychain integration through the Python keyring ecosystem.

```sh
cd /Volumes/edata/codex/dev/git/AgentBlaster
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,secrets]"
agentblaster --help
```

If optional extras are not available in the current package version, install the editable package first and inspect the command surface:

```sh
python -m pip install -e .
agentblaster --help
```

## 4. Configure providers

Providers should be explicit. A benchmark claim should always identify the provider contract, base URL, model name, declared capabilities, authentication mode, and policy restrictions.

### 4.1 Local AFM-style OpenAI-compatible provider

```sh
agentblaster providers add-preset --preset afm
agentblaster providers show afm
agentblaster providers check-suite --provider afm --suite smoke
```

Manual equivalent:

```sh
agentblaster providers add \
  --name afm \
  --contract openai \
  --base-url http://127.0.0.1:9999/v1 \
  --default-model mlx-community/Qwen3.6-27B
```

### 4.2 Local LM Studio or Ollama-style provider

Use the same provider shape, but point the base URL at the local server.

```sh
agentblaster providers add \
  --name lmstudio-local \
  --contract openai \
  --base-url http://127.0.0.1:1234/v1 \
  --default-model local-model-name
```

```sh
agentblaster providers add \
  --name ollama-local \
  --contract openai \
  --base-url http://127.0.0.1:11434/v1 \
  --default-model qwen3.6:27b
```

### 4.3 Remote OpenAI-compatible provider

For internet-facing providers, prefer environment-variable references or keyring-backed secrets over plain text configuration.

```sh
export OPENAI_API_KEY="..."
agentblaster providers add-preset --preset openai --name openai-remote
agentblaster providers auth set --provider openai-remote --api-key-env OPENAI_API_KEY
agentblaster providers check-suite --provider openai-remote --suite smoke
```

### 4.4 Remote Anthropic-compatible provider

```sh
export ANTHROPIC_API_KEY="..."
agentblaster providers add \
  --name anthropic-remote \
  --contract anthropic \
  --base-url https://api.anthropic.com \
  --default-model claude-sonnet-4
agentblaster providers auth set --provider anthropic-remote --api-key-env ANTHROPIC_API_KEY
```

### 4.5 Optional keyring support

Keyring support should be optional. On macOS it can map to Apple Keychain. On Linux and Windows it should use the platform backend when available. In CI, environment-variable references are usually better because they are auditable and ephemeral.

```sh
agentblaster providers auth set --help
```

Recommended credential order:

| Context | Preferred credential method |
| --- | --- |
| Local macOS development | Platform keyring or environment-variable reference. |
| Linux development | Platform keyring where available, otherwise environment-variable reference. |
| Windows development | Windows Credential Manager through keyring where available, otherwise environment-variable reference. |
| CI | CI-managed secret injected as an environment variable. |
| Shared benchmark config | Secret reference only, never the secret value. |

## 5. Declare provider capabilities

AgentBlaster should not infer all provider behavior from one successful request. Declare capabilities so suite planning, skip logic, and strict gates are transparent.

```sh
agentblaster providers capabilities list --provider afm
agentblaster providers check-suite --provider afm --suite toolcall --strict-unknown
```

If a provider supports a capability:

```sh
agentblaster providers capabilities enable --provider afm --capability tool_calling
```

If a provider does not support a capability:

```sh
agentblaster providers capabilities disable --provider afm --capability structured_output
```

Common capabilities:

| Capability | Why it matters |
| --- | --- |
| `tool_calling` | Required for agentic workflows that invoke functions, tools, or MCP adapters. |
| `structured_output` | Required for JSON-schema-like output contracts and strict parsing. |
| `streaming` | Required for latency, cancellation, and streaming event correctness tests. |
| `usage_accounting` | Required when provider-reported token statistics are included in scorecards. |
| `parallel_requests` | Required for concurrency and fanout stress suites. |
| `prompt_cache` | Required for prefill and repeated system-prompt pressure tests. |

## 6. Run the first benchmark

Start with smoke. Do not begin with a large matrix until the provider, model, and capabilities are confirmed.

```sh
agentblaster run \
  --engine afm \
  --suite smoke \
  --model mlx-community/Qwen3.6-27B \
  --output-dir runs \
  --no-raw-traces
```

Use a dry run when planning a suite:

```sh
agentblaster run \
  --engine afm \
  --suite toolcall \
  --model mlx-community/Qwen3.6-27B \
  --dry-run
```

Use strict capability handling when the run is intended for comparison or publication:

```sh
agentblaster run \
  --engine afm \
  --suite toolcall \
  --model mlx-community/Qwen3.6-27B \
  --strict-unknown-capabilities \
  --no-raw-traces
```

## 7. Recommended AFM baseline

For AFM and other local MLX engines, start with this progression:

| Step | Suite | Purpose |
| --- | --- | --- |
| 1 | `smoke` | Confirm endpoint, model, basic response, and usage collection. |
| 2 | `toolcall` | Validate OpenAI-style tool call behavior and argument quality. |
| 3 | `structured-output` | Validate JSON and schema-following behavior. |
| 4 | `long-system-prompt` | Measure repeated large system prompt pressure and prefill behavior. |
| 5 | `concurrency` | Measure correctness and stability under parallel work. |
| 6 | `cache-control` | Measure repeated prompt caching and cache-invalidation behavior. |
| 7 | `tool-loop` | Exercise multi-step tool workflows and loop termination. |
| 8 | `harness-engineering` | Test emerging harness patterns, self-repair behavior, and orchestration sensitivity. |

Initial model matrix:

| Model | Role |
| --- | --- |
| Qwen3.6 27B dense | Primary local agentic benchmark target. |
| Gemma 4 dense | Secondary dense architecture comparison target. |

## 8. Run a matrix

Matrices are the preferred way to compare providers, models, suites, and runtime settings.

```sh
agentblaster run \
  --matrix examples/matrices/qwen-gemma-stress.yaml \
  --output-dir runs \
  --matrix-summary-json reports/qwen-gemma-matrix-summary.json \
  --continue-on-error
```

Apply a gate to turn the matrix into a decision artifact:

```sh
agentblaster matrix gate reports/qwen-gemma-matrix-summary.json \
  --max-failed-runs 0 \
  --min-case-pass-rate 95 \
  --max-invalid-tool-calls 0 \
  --min-tool-parser-repair-valid-rate 95 \
  --include-failure-class-summary \
  --include-tool-loop-summary \
  --include-tool-parser-repair-summary \
  --output-json reports/qwen-gemma-matrix-gate.json
```

A serious external claim should not rely on a single run. Use repeated runs, fixed suite versions, fixed model IDs, fixed provider configs, and an explicit artifact bundle.

## 9. Generate reports

Generate human-readable and machine-readable outputs from the run directory.

```sh
agentblaster report runs/<run-id> --format html,json,publication,card,pdf
```

Create a publication bundle:

```sh
agentblaster publication-bundle runs/<run-id> --output-dir publication-bundles
```

Recommended report outputs:

| Output | Audience |
| --- | --- |
| JSON | Automation, CI, dashboards, and reproducibility checks. |
| HTML | Interactive review and internal sharing. |
| Markdown | Pull requests, engineering notes, and decision records. |
| PDF | Corporate sharing and archive snapshots. |
| Publication bundle | Media posts, vendor comparisons, and public claims. |

## 10. Evidence and governance

Evidence artifacts are used to defend benchmark conclusions. They should include enough metadata to reproduce the result without exposing secrets or raw private content.

```sh
agentblaster evidence bundle \
  --suite smoke \
  --output-dir evidence \
  --include-provider-audit
```

```sh
agentblaster providers audit --output-json reports/provider-audit.json
agentblaster security posture --output-json reports/security-posture.json
```

Use the evidence command help if subcommands change:

```sh
agentblaster evidence --help
```

Minimum evidence for serious comparison:

| Artifact | Purpose |
| --- | --- |
| Provider audit | Records contract, endpoint class, model, declared capabilities, and credential handling mode. |
| Matrix summary | Records all planned and completed runs. |
| Matrix gate | Converts results into pass, fail, and warning decisions. |
| Security posture | Confirms redaction, retention, remote-access, and secret-handling posture. |
| Publication bundle | Provides a compact, sanitized package for external communication. |

## 11. Release qualification

Release qualification is used when an engine is being promoted as better, safer, faster, or more production-ready.

```sh
agentblaster release implementation-status \
  --output reports/implementation-status.json
```

```sh
agentblaster release protocol-repair \
  --matrix-scorecard reports/matrix-scorecard.json \
  --matrix-gate reports/qwen-gemma-matrix-gate.json \
  --output-json reports/protocol-repair.json
```

```sh
agentblaster release workflow-readiness \
  --artifact reports/qwen-gemma-matrix-gate.json \
  --output-json reports/workflow-readiness.json
```

```sh
agentblaster release claim-readiness \
  --matrix-gate reports/qwen-gemma-matrix-gate.json \
  --output-json reports/claim-readiness.json
```

```sh
agentblaster release qualification-bundle \
  --name qwen-gemma-local \
  --output-dir release-bundles \
  --matrix-gate reports/qwen-gemma-matrix-gate.json
```

Before publishing a claim, check that the benchmark states the model, provider, hardware class, operating system, suite version, run date, policy, and known limitations.

## 12. Dashboard

The dashboard is optional. Use it for setup, launch, inspection, and report creation when CLI output is not enough.

```sh
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765
```

Dashboard security expectations:

| Setting | Requirement |
| --- | --- |
| Loopback host | Default for local development. |
| Non-loopback host | Require explicit operator intent, authentication, and policy approval. |
| API keys | Never display full values. |
| Raw traces | Redacted by default and opt-in only. |
| Exported reports | Use compact summaries unless raw evidence is explicitly authorized. |

For GUI testing, use the project test harness and browser automation. If Chromium binaries are missing for Playwright or the Chrome-based test plugin, install them only when you intend to run GUI tests.

```sh
python -m playwright install chromium
```

## 13. Security operating model

AgentBlaster should be usable in enterprise environments. Treat benchmark data like production-adjacent data because it may contain prompts, code snippets, internal tool names, endpoint metadata, and provider credentials.

Security defaults:

| Area | Default |
| --- | --- |
| API keys | Use environment variables, CI secrets, or optional keyring support. |
| Local config | Store secret references, not secret values. |
| Raw traces | Disabled or redacted unless explicitly enabled. |
| Report exports | Compact and sanitized by default. |
| Remote providers | Declared explicitly and governed by policy. |
| Retention | Keep artifacts only as long as needed for benchmark evidence. |
| Logging | Avoid headers, secrets, raw tool arguments, and private prompts. |
| Dashboard | Bind to loopback unless explicitly configured otherwise. |

Operational rules:

| Rule | Rationale |
| --- | --- |
| Never paste API keys into benchmark YAML or documentation. | Prevents accidental source control exposure. |
| Prefer deterministic suite definitions. | Makes comparisons reproducible. |
| Keep raw and redacted artifacts separate. | Allows publication without leaking sensitive content. |
| Treat remote engines as data egress. | Prompts and tool outputs may leave the machine. |
| Record policy exceptions. | Enterprise reviewers need a decision trail. |

## 14. Output directories

Recommended local layout:

| Directory | Contents |
| --- | --- |
| `runs/` | Per-run traces, summaries, timings, and normalized metrics. |
| `reports/` | Matrix gates, scorecards, security posture, and generated report files. |
| `evidence/` | Evidence bundles for reproducibility and audit. |
| `publication-bundles/` | Sanitized packages for media or corporate sharing. |
| `release-bundles/` | Qualification artifacts for release decisions. |

Large raw traces should not be committed unless intentionally captured, redacted, and approved.

## 15. Troubleshooting

| Symptom | Action |
| --- | --- |
| `unknown provider` | Run `agentblaster providers list`, then add or correct the provider name. |
| Provider check fails | Confirm base URL, model name, server status, and API key reference. |
| Capability is unknown | Declare the capability or remove strict capability enforcement. |
| Tool-call tests fail | Inspect normalized tool-call arguments, invalid tool-call counts, and repair metrics. |
| Structured output tests fail | Compare raw text, parsed JSON, schema errors, and repair behavior. |
| Concurrency tests are unstable | Lower concurrency, isolate provider state, and check engine logs. |
| Cache tests are noisy | Confirm prompt cache support, cache policy, and warmup behavior. |
| Publication bundle fails | Generate publication-format reports first, then rebuild the bundle. |
| GUI tests are skipped | Install browser binaries only if GUI testing is required. |
| Remote provider blocked | Check policy settings, network allowlists, and credential configuration. |

## 16. Recommended benchmark path for AFM improvement

Use this path when the goal is to make AFM the strongest local AI engine for agentic work:

1. Establish an AFM smoke baseline with Qwen3.6 27B dense.
2. Add Gemma 4 dense as a second dense-model comparison point.
3. Run tool calling, structured output, tool-loop, long-system-prompt, cache-control, concurrency, and harness-engineering suites.
4. Compare AFM against oMLX, Ollama MLX, Rapid MLX, and LM Studio using the same suite versions and hardware notes.
5. Track failures by taxonomy instead of only by pass rate.
6. Prioritize fixes that improve protocol fidelity, parser repair validity, concurrency stability, and prefill efficiency.
7. Re-run the same matrix after each engine improvement and preserve the matrix gate artifact.
8. Publish only redacted scorecards and evidence bundles.

## 17. SDLC expectations

AgentBlaster should include its own testing harness. The benchmark suite itself must be tested with normal software delivery practices.

Expected project tests:

| Test type | Purpose |
| --- | --- |
| Unit tests | Validate parsers, scoring, artifact generation, redaction, and provider config logic. |
| Contract tests | Validate OpenAI-compatible and Anthropic-compatible request and response handling. |
| Golden artifact tests | Prevent accidental schema, report, and scorecard regressions. |
| Integration tests | Exercise local mock providers and controlled API responses. |
| CLI tests | Validate command behavior, exit codes, help text, and error messages. |
| GUI tests | Validate dashboard flows with browser automation and Chrome-based testing where available. |
| Security tests | Validate secret redaction, unsafe config detection, and artifact sanitization. |
| Performance sanity tests | Detect obvious regressions in benchmark harness overhead. |

Do not treat benchmark results as credible if the benchmark harness is not itself tested.

## 18. Documentation maintenance

Update documentation when any of these change:

| Change | Required documentation update |
| --- | --- |
| New suite | Add purpose, inputs, metrics, expected artifacts, and limitations. |
| New provider type | Add setup, authentication, capability, and security notes. |
| New report artifact | Update artifact schema and reporting documentation. |
| New gate | Document thresholds, failure modes, and intended decision use. |
| New security behavior | Update security policy, retention, and user guide. |
| New dashboard workflow | Update dashboard and GUI testing notes. |

Documentation should describe what the tool actually does, not what it intends to do later. Future behavior belongs in planning or PRD documents until implemented.

