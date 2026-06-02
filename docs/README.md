# AgentBlaster Documentation

AgentBlaster is a benchmark suite for local and remote agentic AI engines. It is designed to compare OpenAI-compatible and Anthropic-compatible APIs across tool use, structured outputs, long prompts, concurrency, cache behavior, MCP-style workflows, and emerging harness-engineering patterns.

This documentation is written for operators, developers, evaluators, and technical decision makers who need reproducible benchmark results that can survive internal review, media publication, or enterprise procurement scrutiny.

## Start here

| Need | Document |
| --- | --- |
| Run the benchmark suite | [User guide](user-guide.md) |
| Understand product intent and scope | [Product requirements](prd.md) |
| Configure local or remote engines | [Provider model](providers.md) |
| Apply enterprise security expectations | [Security policy](security-policy.md) |
| Create media or corporate-ready results | [Reporting](reporting.md) |
| Qualify a release or compare engines | [Release qualification](release-qualification.md) |
| Understand workflow coverage | [Workflow surfaces](workflow-surfaces.md) |
| Understand generated files | [Artifact schemas](artifact-schemas.md) |

## Documentation map

| Area | Documents |
| --- | --- |
| Getting started | [User guide](user-guide.md), [Providers](providers.md), [Models](models.md), [Suite governance](suite-governance.md) |
| Benchmark execution | [Planning](planning.md), [Trace replay](trace-replay.md), [Cache control](cache-control.md), [Cancellation](cancellation.md), [Agent fanout](agent-fanout.md), [Workflow surfaces](workflow-surfaces.md), [Harness](harness.md), [Harness engineering](harness-engineering.md) |
| Results and governance | [Reporting](reporting.md), [Evidence bundles](evidence-bundles.md), [Release qualification](release-qualification.md), [Artifact schemas](artifact-schemas.md), [Failure taxonomy](failure-taxonomy.md), [Telemetry normalization](telemetry-normalization.md), [Metrics](metrics.md), [Observability](observability.md) |
| Security and enterprise readiness | [Security policy](security-policy.md), [Retention](retention.md), [Security scan](security-scan.md), [Audit](audit.md), [Reproducibility](reproducibility.md) |
| Operations and reference | [Dashboard](dashboard.md), [Launch recipes](launch-recipes.md), [Capabilities](capabilities.md), [Engine targets](engine-targets.md), [Prompt footprint](prompt-footprint.md), [Testing](testing.md) |

## Typical workflow

1. Configure one or more providers with local, remote, or CI-safe credentials.
2. Run a smoke suite to confirm the provider contract, model name, and declared capabilities.
3. Run targeted suites for tool calling, structured output, concurrency, cache behavior, and harness engineering.
4. Generate compact reports and evidence bundles.
5. Apply release gates before publishing claims or comparing engines.
6. Use the dashboard for interactive inspection when a CLI report is not enough.

## Security baseline

AgentBlaster documentation assumes a security-first operating model:

| Principle | Requirement |
| --- | --- |
| No secrets in artifacts | Use environment variables, platform keyring support, or CI secret references instead of hard-coded API keys. |
| Redacted by default | Prefer compact summaries and redacted traces for reports, bundles, and dashboard exports. |
| Explicit remote access | Remote internet-facing providers should be declared and governed by policy. |
| Evidence over anecdotes | Published claims should link to reproducible run metadata, normalized metrics, and release gates. |
| Enterprise reviewability | Security posture, provider audit, retention, and artifact schemas should be available with each serious benchmark claim. |

Raw provider payloads, API keys, customer data, private prompts, and unredacted traces should not be copied into documentation, reports, or public benchmark artifacts.

## Primary benchmark targets

Initial target architectures:

| Model family | Benchmark intent |
| --- | --- |
| Qwen3.6 27B dense | Stress local agentic workloads with stronger tool-use and reasoning-oriented behavior. |
| Gemma 4 dense | Provide a second dense-model comparison point across the same workflow surfaces. |

Initial engine focus:

| Engine class | Examples |
| --- | --- |
| Local MLX and Mac engines | AFM MLX, oMLX, Ollama MLX, Rapid MLX, LM Studio |
| Remote OpenAI-compatible APIs | OpenAI-compatible inference services and hosted gateways |
| Remote Anthropic-compatible APIs | Anthropic-style message APIs and compatible gateways |

AgentBlaster should not assume that a provider reports performance statistics consistently. The benchmark normalizes reported and measured telemetry so each engine can be compared on the same evidence model.

