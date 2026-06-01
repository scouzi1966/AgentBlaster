# AgentBlaster

AgentBlaster is a local agentic benchmark suite for OpenAI-compatible, Anthropic-compatible, and engine-native local inference servers.

The goal is to measure the hard parts of local agent workloads: repeated long system prompts, tool schemas, skills, MCP-style tool catalogs, structured output, streaming, cancellation, concurrency, prompt-cache reuse, and professional reporting.

[![CI](https://github.com/scouzi1966/AgentBlaster/actions/workflows/ci.yml/badge.svg)](https://github.com/scouzi1966/AgentBlaster/actions/workflows/ci.yml)

## Initial Scope

- Engines: AFM MLX, mlx-lm, Ollama MLX, LM Studio, oMLX, Rapid-MLX, and vLLM-MLX.
- Models: Qwen3.6-27B dense and Gemma 4 31B dense.
- Interfaces: OpenAI Chat Completions first, then OpenAI Responses and Anthropic Messages.
- Outputs: CLI results, normalized JSONL, optional dashboard, HTML/PDF/PNG reports.

## Repository Status

This repository is freshly scaffolded from the initial PRD. The product requirements live in [docs/prd.md](docs/prd.md).

## Implemented CLI Foundation

```bash
agentblaster version
agentblaster suites
agentblaster validate-case examples/suites/smoke.yaml
agentblaster engines list
agentblaster engines launch-recipes --catalog
agentblaster engines launch-recipes --engine afm --model mlx-community/Qwen3.6-27B --markdown --output-json reports/afm-launch-recipe.json
agentblaster engines probe --engine afm --base-url http://127.0.0.1:9999/v1
agentblaster providers presets
agentblaster providers add-preset --preset afm
agentblaster providers add-preset --preset ollama-native
agentblaster providers add-preset --preset openai
agentblaster providers add-preset --preset anthropic
agentblaster providers add-preset --preset openai --name openai-workspace --api-key-env WORKSPACE_OPENAI_KEY
agentblaster providers add --name openai --contract openai --base-url https://api.openai.com/v1 --api-key-env OPENAI_API_KEY --remote
agentblaster providers add --name openai --contract openai --base-url https://api.openai.com/v1 --api-key-env OPENAI_API_KEY --remote --audit-log audit/control-plane.jsonl
agentblaster providers add --name openai-enterprise --contract openai --base-url https://gateway.example.com/v1 --api-key-env OPENAI_API_KEY --ca-bundle /etc/ssl/certs/enterprise-ca.pem --remote
agentblaster providers list
agentblaster providers audit --policy agentblaster.policy.yaml --output-json reports/provider-audit.json
agentblaster providers metric-coverage --provider afm --output-json reports/afm-metric-coverage.json
agentblaster providers metric-coverage --catalog --output-json reports/metric-coverage-catalog.json
agentblaster providers readiness --provider afm --suite trace-replay --model mlx-community/Qwen3.6-27B --policy agentblaster.policy.yaml --strict-unknown --output-json reports/afm-trace-readiness.json
agentblaster mock-provider --host 127.0.0.1 --port 8787
agentblaster providers contract-check --provider mock-openai --model agentblaster-mock-qwen3.6-27b-dense --output-json reports/mock-openai-contract-plan.json
agentblaster providers contract-check --provider mock-openai --model agentblaster-mock-qwen3.6-27b-dense --execute --output-json reports/mock-openai-contract-check.json
agentblaster providers auth test --provider openai
agentblaster providers auth status --provider openai
agentblaster providers auth clear --provider openai --delete-secret
agentblaster providers cost set --provider openai --input-usd-per-1m-tokens 3.0 --output-usd-per-1m-tokens 12.0
agentblaster providers cost show --provider openai
agentblaster providers rate-limits set --provider openai --max-concurrency 2 --requests-per-minute 60
agentblaster providers rate-limits show --provider openai
agentblaster providers probe openai
agentblaster providers capabilities enable --provider afm --capability tool_calling
agentblaster providers capabilities list --provider afm
agentblaster suite-requirements --suite trace-replay
agentblaster suite-footprint --suite trace-replay --output-json reports/trace-replay-footprint.json
agentblaster suite-footprint --suite cache-control --output-json reports/cache-control-footprint.json
agentblaster suite-audit --suite-file examples/suites/toolsim.yaml --output-json reports/toolsim-suite-audit.json
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --template-output reports/agentic-local-profiles-calibration.json
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --calibration reports/agentic-local-profiles-calibration.json --output-json reports/agentic-local-profiles-calibration-report.json
agentblaster policy validate agentblaster.policy.yaml --output-json reports/policy-normalized.json
agentblaster evidence bundle --suite-file examples/suites/toolsim.yaml --policy agentblaster.policy.yaml --include-provider-audit --output-dir evidence --audit-log audit/control-plane.jsonl
agentblaster providers check-suite --provider openai --suite trace-replay --output-json reports/openai-trace-preflight.json
agentblaster providers check-suite --provider afm --suite toolcall --strict-unknown
agentblaster catalog simulated-tools --output-json reports/simulated-tools-catalog.json
agentblaster catalog mcp-profiles --output-json reports/mcp-profiles-catalog.json
agentblaster catalog skills --output-json reports/skills-catalog.json
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765 --policy agentblaster.policy.yaml --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --dry-run --plan-json reports/afm-smoke-plan.json
agentblaster run --suite smoke --engine openai --model <openai-model> --no-raw-traces --audit-log runs/audit.jsonl --concurrency 1 --retention-classification confidential --retention-days 30 --raw-trace-retention-days 7
agentblaster run --suite-file examples/suites/smoke.yaml --engine openai --model <openai-model> --no-raw-traces
agentblaster run --suite toolcall --engine afm --model mlx-community/Qwen3.6-27B --strict-unknown-capabilities
agentblaster run --matrix examples/matrices/local-smoke.yaml --offline --continue-on-error --matrix-summary-json reports/local-smoke-matrix-summary.json
agentblaster matrix report reports/local-smoke-matrix-summary.json --format html,md,json
agentblaster matrix gate reports/local-smoke-matrix-summary.json --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95 --output-json reports/local-smoke-matrix-gate.json
agentblaster run --suite trace-replay --engine afm --model mlx-community/Qwen3.6-27B --offline
agentblaster run --suite-file examples/suites/trace-replay.yaml --engine afm --model mlx-community/Qwen3.6-27B --offline
agentblaster report runs/<run-id> --format html,json,publication,card
agentblaster report runs/<run-id> --format html,json --audit-log audit/control-plane.jsonl
agentblaster publication-bundle runs/<run-id> --output-dir publication-bundles --audit-log audit/control-plane.jsonl
agentblaster export runs/<run-id> --format jsonl,csv
agentblaster compare runs/<run-a> runs/<run-b> --output-json reports/comparison.json
agentblaster compare-gate runs/<baseline> runs/<candidate> --max-avg-latency-regression-pct 15 --min-pass-rate 95 --output-json reports/comparison-gate.json
agentblaster cleanup runs/<run-id> --raw --reports --exports
agentblaster cleanup-expired --runs runs --output-json reports/cleanup-plan.json
agentblaster cleanup-expired --runs runs --execute --audit-log audit/control-plane.jsonl
agentblaster verify runs/<run-id>
agentblaster sign runs/<run-id> --key-env AGENTBLASTER_SIGNING_KEY --key-id ci-release-key
agentblaster verify-signature runs/<run-id> --key-env AGENTBLASTER_SIGNING_KEY
agentblaster quality tiers
agentblaster quality command normal
agentblaster quality chrome-checklist --output tests/gui/chrome-dashboard-checklist.md
agentblaster quality chrome-plan --format json --output tests/gui/chrome-dashboard-plan.json
agentblaster quality dashboard-fixture --output tests/fixtures/dashboard-runs --overwrite
agentblaster selftest --tier normal --dry-run
agentblaster selftest gui --browser chromium --headed --dry-run
PYTHONPATH=src pytest -q tests/gui -m gui
agentblaster selftest report --run selftest_20260531T000000Z --format html,json,junit
agentblaster experiment manifest --name qwen-gemma-local --objective "Compare AFM and LM Studio on Qwen/Gemma local-agent suites." --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suites trace-replay,prefill --policy agentblaster.policy.yaml --output reports/qwen-gemma-experiment.json
agentblaster experiment gate reports/qwen-gemma-experiment.json --require-policy --output-json reports/qwen-gemma-experiment-gate.json
agentblaster release provenance --output reports/release-provenance.json --audit-log audit/control-plane.jsonl
agentblaster release qualification-bundle --name afm-release --evidence-bundle evidence/toolsim.agentblaster-evidence.zip --matrix-gate reports/qwen-gemma-matrix-gate.json --release-provenance reports/release-provenance.json --output-dir release-bundles --audit-log audit/control-plane.jsonl
agentblaster security scan release-bundles/afm-release.agentblaster-release-qualification.zip --output-json reports/redaction-scan.json
agentblaster agents profiles
agentblaster agents suite --profile all --output examples/suites/agentic-local-profiles.yaml
agentblaster harness profiles
agentblaster harness generate --profile contract-fuzz --suite smoke --repeats 1 --seed 0 --output examples/suites/harness-contract-fuzz.yaml
agentblaster harness generate --profile metamorphic --suite smoke --repeats 3 --seed 13 --output examples/suites/harness-metamorphic.yaml
agentblaster models targets
agentblaster models matrix --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suite trace-replay --output examples/matrices/qwen-gemma-local.yaml
agentblaster models stress-matrix --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suites prefill,trace-replay --concurrency-levels 1,2,4,8 --output examples/matrices/qwen-gemma-stress.yaml --summary-json reports/qwen-gemma-stress-plan.json
agentblaster models benchmark-kit --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suite trace-replay --policy agentblaster.policy.yaml --output-dir benchmark-kits/qwen-gemma-local
agentblaster run --matrix examples/matrices/qwen-gemma-local.yaml --offline --continue-on-error --matrix-summary-json reports/qwen-gemma-matrix-summary.json
agentblaster matrix report reports/qwen-gemma-matrix-summary.json --format html,md,json
agentblaster matrix gate reports/qwen-gemma-matrix-summary.json --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95 --output-json reports/qwen-gemma-matrix-gate.json
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --offline
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --policy agentblaster.policy.yaml
```

Provider profiles are stored locally without raw API keys. API keys can be referenced through environment variables or optional OS keyring storage with explicit status, test, clear, and keyring-delete workflows.

Provider setup details are documented in [docs/providers.md](docs/providers.md), including remote OpenAI/Anthropic presets, the deterministic local mock provider, readiness dossiers, portable environment-variable or optional OS-keyring API-key references, cost models for budget policy, and provider rate limits for pacing/concurrency control. Local engine setup recipes are documented in [docs/launch-recipes.md](docs/launch-recipes.md).

Reporting details are documented in [docs/reporting.md](docs/reporting.md), including publication JSON and SVG report cards for media or corporate consumption. Metric coverage is documented in [docs/metrics.md](docs/metrics.md), including native/measured/inferred/conditional/unavailable field status for cross-engine comparisons.

Reproducibility details are documented in [docs/reproducibility.md](docs/reproducibility.md), including suite snapshots, suite/case hashes, and run integrity manifests.
Retention metadata is documented in [docs/retention.md](docs/retention.md), including manifest fields for artifact classification, intended run retention, and shorter raw-trace retention.

Observability details are documented in [docs/observability.md](docs/observability.md), including optional Prometheus before/after snapshots for local engine telemetry. Cache-control diagnostics are documented in [docs/cache-control.md](docs/cache-control.md).

Dashboard details are documented in [docs/dashboard.md](docs/dashboard.md), including the no-JavaScript launch/report-generation forms and allowlisted report artifact links.

Capability preflight is documented in [docs/capabilities.md](docs/capabilities.md), including suite feature requirements and provider-suite compatibility checks.
Run execution performs capability preflight by default, failing before dispatch when a provider is explicitly missing suite-required features.
Bundled capability surface catalogs are documented in [docs/capability-surfaces.md](docs/capability-surfaces.md), including simulated tool, MCP profile, and skill-pack inventory commands for policy review.
Suite governance is documented in [docs/suite-governance.md](docs/suite-governance.md), including static provenance, risk, license/source, and capability-surface audits before dispatch.
Evidence bundles are documented in [docs/evidence-bundles.md](docs/evidence-bundles.md), including redaction-safe governance zip artifacts for corporate review and media-supporting benchmark evidence.

Model targets, matrix generation, and benchmark kits are documented in [docs/models.md](docs/models.md), including the initial Qwen3.6 27B dense and Gemma 4 31B dense comparison targets.

Dry-run planning is documented in [docs/planning.md](docs/planning.md), including policy/capability preflight and estimated token/cost summaries before dispatch. Prompt footprint analysis is documented in [docs/prompt-footprint.md](docs/prompt-footprint.md), including system/tool/MCP/skill prefix breakdowns for prefill diagnostics.

Run execution includes enterprise controls: raw traces can be disabled, remote providers can be blocked with `--offline`, YAML policy files can allowlist providers and endpoint hosts, policy can require remote API-key references, policy can restrict secret backends, policy can cap suite and matrix cost exposure, policy can gate suite-provided tool schemas, simulated tools, MCP profiles, skills, provenance, risk levels, and source/license metadata, and optional JSONL audit logs record run and policy events.
Security policy details are documented in [docs/security-policy.md](docs/security-policy.md). The example policy in [agentblaster.policy.example.yaml](agentblaster.policy.example.yaml) separates provider endpoint allowlists from Prometheus metrics endpoint allowlists and includes capability-surface allowlists.

Audit logging details are documented in [docs/audit.md](docs/audit.md), including control-plane events for provider config, secret reference changes, dashboard start, report generation, matrix reports, and exports.

AgentBlaster includes its own SDLC test harness taxonomy. The `quality` commands describe deterministic app-test tiers, release lanes, Chrome/Codex dashboard validation plans, and redacted dashboard fixtures without running tests.
Experiment manifests are documented in [docs/experiments.md](docs/experiments.md), including static scope, preflight requirements, acceptance gates, and publication rules for corporate/media benchmark campaigns. Release governance artifacts can be generated with `agentblaster release provenance`; the JSON output records project metadata, dependency declarations, optional installed package inventory, safe source hashes, and explicit redaction notes. Release qualification bundles collect evidence, gate, provenance, publication, and selftest artifacts into one checksum-indexed package. Use `agentblaster security scan` as a final local redaction gate before publishing bundles.

AgentBlaster includes representative local-agent profile generators for OpenCode-style, OpenClaw-style, Hermes-style, and Pi-style workflows. The `agents` commands write reviewable YAML suites and do not call providers.

AgentBlaster also includes deterministic harness-engineering generators for prefill/cache, concurrency, provider-contract fuzz, and metamorphic-equivalence workloads. The `harness` commands write reviewable YAML suites and do not call providers.
Harness engineering details are documented in [docs/harness.md](docs/harness.md), including generated-suite provenance and reporting metadata.

Trace replay cases can provide explicit `messages` for multi-turn agent workflows, including prior assistant tool calls and deterministic tool-result context. OpenAI-compatible and Anthropic-compatible adapters normalize those traces into their respective request contracts.

## Planned Benchmark CLI

```bash
agentblaster report runs/<run-id> --format html
```
