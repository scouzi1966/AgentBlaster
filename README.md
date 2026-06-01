# AgentBlaster

AgentBlaster is a local agentic benchmark suite for OpenAI-compatible, Anthropic-compatible, and engine-native local inference servers.

The goal is to measure the hard parts of local agent workloads: repeated long system prompts, tool schemas, skills, MCP-style tool catalogs, structured output, streaming, cancellation, concurrency, prompt-cache reuse, and professional reporting.

[![CI](https://github.com/scouzi1966/AgentBlaster/actions/workflows/ci.yml/badge.svg)](https://github.com/scouzi1966/AgentBlaster/actions/workflows/ci.yml)

## Initial Scope

- Engines: AFM MLX, mlx-lm, Ollama MLX, LM Studio, oMLX, Rapid-MLX, and vLLM-MLX.
- Models: Qwen3.6-27B dense and Gemma 4 31B dense.
- Interfaces: OpenAI Chat Completions first, then OpenAI Responses and Anthropic Messages.
- Outputs: CLI results, normalized JSONL, optional dashboard, HTML/PDF/SVG reports, PNG-ready media cards, and media-kit manifests for corporate/media publication packs.

## Repository Status

This repository is freshly scaffolded from the initial PRD. The product requirements live in [docs/prd.md](docs/prd.md).

## Implemented CLI Foundation

```bash
agentblaster version
agentblaster doctor --policy agentblaster.policy.yaml --output-json reports/environment-readiness.json
agentblaster implementation-status --output-json reports/implementation-status.json
agentblaster suites
agentblaster validate-case examples/suites/smoke.yaml
agentblaster engines list
agentblaster engines onboarding --format markdown --output reports/local-engine-onboarding.md
agentblaster engines improvement-plan --engine afm --pressure-audit reports/qwen-gemma-stress-pressure.json --matrix-saturation-report reports/qwen-gemma-matrix-saturation.json --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json --telemetry-audit reports/afm-telemetry-audit.json --metric-coverage reports/afm-metric-coverage.json --matrix-gate reports/qwen-gemma-matrix-gate.json --harness-review reports/harness-orchestration-review.json --output-json reports/afm-improvement-plan.json
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
agentblaster suite-requirements --suite agentic-tool-loop
agentblaster suite-requirements --suite agent-fanout
agentblaster suite-requirements --suite cancellation
agentblaster suite-footprint --suite trace-replay --output-json reports/trace-replay-footprint.json
agentblaster suite-footprint --suite cache-control --output-json reports/cache-control-footprint.json
agentblaster suite-audit --suite-file examples/suites/toolsim.yaml --output-json reports/toolsim-suite-audit.json
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --template-output reports/agentic-local-profiles-calibration.json
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --calibration reports/agentic-local-profiles-calibration.json --output-json reports/agentic-local-profiles-calibration-report.json
agentblaster policy validate agentblaster.policy.yaml --output-json reports/policy-normalized.json
agentblaster policy template --profile local --output agentblaster.policy.yaml --output-json reports/enterprise-policy-template.json
agentblaster policy controls agentblaster.policy.yaml --name local-campaign --output-json reports/policy-control-summary.json
agentblaster evidence bundle --suite-file examples/suites/toolsim.yaml --policy agentblaster.policy.yaml --include-provider-audit --output-dir evidence --audit-log audit/control-plane.jsonl
agentblaster evidence campaign-preflight --matrix examples/matrices/qwen-gemma-local.yaml --matrix examples/matrices/qwen-gemma-stress.yaml --policy agentblaster.policy.yaml --benchmark-readiness reports/afm-trace-readiness.json --output-dir campaign-preflight/qwen-gemma-local --audit-log audit/control-plane.jsonl
agentblaster evidence campaign-preflight --matrix campaigns/qwen-gemma-local/matrices/qwen-gemma-local.yaml --policy agentblaster.policy.yaml --benchmark-readiness-list campaigns/qwen-gemma-local/reports/benchmark-readiness-inputs.txt --output-dir campaigns/qwen-gemma-local/reports/campaign-preflight
agentblaster evidence index --name afm-release --artifact reports/qwen-gemma-matrix-gate.json --artifact reports/harness-orchestration-review.json --artifact reports/afm-improvement-plan.json --artifact reports/afm-metric-coverage.json --artifact reports/cleanup-plan.json --output-json reports/afm-release-evidence-index.json
agentblaster providers check-suite --provider openai --suite trace-replay --output-json reports/openai-trace-preflight.json
agentblaster providers check-suite --provider afm --suite toolcall --strict-unknown
agentblaster catalog simulated-tools --output-json reports/simulated-tools-catalog.json
agentblaster catalog mcp-profiles --output-json reports/mcp-profiles-catalog.json
agentblaster catalog lcp-profiles --output-json reports/lcp-profiles-catalog.json
agentblaster catalog skills --output-json reports/skills-catalog.json
agentblaster catalog artifact-schemas --format markdown --output reports/artifact-schemas.md
agentblaster catalog normalize-telemetry samples/ollama-response.json --contract native --native-adapter ollama --output-json reports/ollama-normalized-telemetry.json
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765 --policy agentblaster.policy.yaml --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --dry-run --plan-json reports/afm-smoke-plan.json
agentblaster run --suite smoke --engine openai --model <openai-model> --no-raw-traces --audit-log runs/audit.jsonl --concurrency 1 --retention-classification confidential --retention-days 30 --raw-trace-retention-days 7
agentblaster run --suite-file examples/suites/smoke.yaml --engine openai --model <openai-model> --no-raw-traces
agentblaster run --suite toolcall --engine afm --model mlx-community/Qwen3.6-27B --strict-unknown-capabilities
agentblaster run --suite agentic-tool-loop --engine afm --model mlx-community/Qwen3.6-27B --strict-unknown-capabilities --no-raw-traces
agentblaster run --suite agent-fanout --engine afm --model mlx-community/Qwen3.6-27B --concurrency 4 --no-raw-traces
agentblaster run --suite cancellation --engine afm --model mlx-community/Qwen3.6-27B --no-raw-traces
agentblaster run --suite harness-engineering --engine afm --model mlx-community/Qwen3.6-27B --strict-unknown-capabilities --no-raw-traces
agentblaster run --matrix examples/matrices/local-smoke.yaml --offline --continue-on-error --matrix-summary-json reports/local-smoke-matrix-summary.json
agentblaster matrix contract-checks examples/matrices/qwen-gemma-local.yaml --output-json reports/qwen-gemma-contract-matrix-plan.json
agentblaster matrix pressure-audit examples/matrices/qwen-gemma-stress.yaml --output-json reports/qwen-gemma-stress-pressure.json
agentblaster matrix report reports/local-smoke-matrix-summary.json --format html,md,json
agentblaster matrix saturation-report reports/qwen-gemma-matrix-summary.json --output-json reports/qwen-gemma-matrix-saturation.json
agentblaster matrix gate reports/local-smoke-matrix-summary.json --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95 --max-failure-class engine_protocol_bug=0 --max-tool-loop-stop-reason max_tool_calls_reached=0 --output-json reports/local-smoke-matrix-gate.json
agentblaster run --suite trace-replay --engine afm --model mlx-community/Qwen3.6-27B --offline
agentblaster run --suite-file examples/suites/trace-replay.yaml --engine afm --model mlx-community/Qwen3.6-27B --offline
agentblaster report runs/<run-id> --format html,json,publication,card,png
agentblaster report runs/<run-id> --format html,json --audit-log audit/control-plane.jsonl
agentblaster publication-bundle runs/<run-id> --output-dir publication-bundles --audit-log audit/control-plane.jsonl
agentblaster export runs/<run-id> --format jsonl,csv,parquet
agentblaster telemetry-audit runs/<run-id> --required-field tokens_per_second_decode --output-json reports/run-telemetry-audit.json
agentblaster compare runs/<run-a> runs/<run-b> --output-json reports/comparison.json
agentblaster compare-gate runs/<baseline> runs/<candidate> --max-avg-latency-regression-pct 15 --min-pass-rate 95 --output-json reports/comparison-gate.json
agentblaster cleanup runs/<run-id> --raw --reports --exports --caches --temp --bundles --output-json reports/manual-cleanup-plan.json
agentblaster cleanup runs/<run-id> --raw --reports --exports --caches --temp --bundles --execute --audit-log audit/control-plane.jsonl --require-audit-log --policy agentblaster.policy.yaml
agentblaster cleanup-expired --runs runs --output-json reports/cleanup-plan.json
agentblaster cleanup-expired --runs runs --execute --audit-log audit/control-plane.jsonl --require-audit-log --policy agentblaster.policy.yaml
agentblaster verify runs/<run-id>
agentblaster sign runs/<run-id> --key-env AGENTBLASTER_SIGNING_KEY --key-id ci-release-key
agentblaster verify-signature runs/<run-id> --key-env AGENTBLASTER_SIGNING_KEY
agentblaster quality tiers
agentblaster quality command normal
agentblaster quality validation-manifest --format json --output test-reports/sdlc-validation-manifest.json
agentblaster quality chrome-checklist --output tests/gui/chrome-dashboard-checklist.md
agentblaster quality chrome-plan --format json --output tests/gui/chrome-dashboard-plan.json
agentblaster quality dashboard-fixture --output tests/fixtures/dashboard-runs --overwrite
agentblaster selftest --tier normal --dry-run
agentblaster selftest gui --browser chromium --headed --dry-run
PYTHONPATH=src pytest -q tests/gui -m gui
agentblaster selftest report --run selftest_20260531T000000Z --format html,json,junit
agentblaster experiment manifest --name qwen-gemma-local --objective "Compare AFM and LM Studio on Qwen/Gemma local-agent suites." --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suites trace-replay,agentic-tool-loop,agent-fanout,prefill,harness-engineering --policy agentblaster.policy.yaml --output reports/qwen-gemma-experiment.json
agentblaster experiment gate reports/qwen-gemma-experiment.json --require-policy --output-json reports/qwen-gemma-experiment-gate.json
agentblaster release packaging-readiness --output-json reports/packaging-readiness.json --fail-on-gaps --audit-log audit/control-plane.jsonl
agentblaster release provenance --output reports/release-provenance.json --audit-log audit/control-plane.jsonl
agentblaster release qualification-bundle --name afm-release --evidence-bundle evidence/toolsim.agentblaster-evidence.zip --provider-audit reports/provider-audit.json --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json --matrix-gate reports/qwen-gemma-matrix-gate.json --telemetry-audit reports/run-telemetry-audit.json --normalized-telemetry reports/afm-normalized-telemetry.json --matrix-pressure-audit reports/qwen-gemma-stress-pressure.json --matrix-saturation-report reports/qwen-gemma-matrix-saturation.json --matrix-scorecard reports/qwen-gemma-matrix-scorecard.json --implementation-status reports/implementation-status.json --campaign-preflight-manifest campaign-preflight/qwen-gemma-local/manifest.json --benchmark-readiness reports/afm-trace-readiness.json --engine-advisory reports/afm-improvement-plan.json --evidence-index reports/afm-release-evidence-index.json --suite-audit reports/toolsim-suite-audit.json --metric-coverage reports/afm-metric-coverage.json --release-provenance reports/release-provenance.json --publication-bundle publication-bundles/run.agentblaster-publication.zip --matrix-publication-bundle publication-bundles/qwen-gemma-matrix-summary.agentblaster-matrix-publication.zip --harness-review reports/harness-contract-fuzz-review.json --selftest-report test-reports/selftest/selftest-report.json --sdlc-validation-manifest test-reports/sdlc-validation-manifest.json --output-dir release-bundles --audit-log audit/control-plane.jsonl
agentblaster security scan release-bundles/afm-release.agentblaster-release-qualification.zip --output-json reports/redaction-scan.json
agentblaster release claim-readiness --name afm-release --experiment-manifest reports/qwen-gemma-experiment.json --experiment-gate reports/qwen-gemma-experiment-gate.json --provider-audit reports/provider-audit.json --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json --matrix-gate reports/qwen-gemma-matrix-gate.json --telemetry-audit reports/run-telemetry-audit.json --normalized-telemetry reports/afm-normalized-telemetry.json --matrix-pressure-audit reports/qwen-gemma-stress-pressure.json --matrix-saturation-report reports/qwen-gemma-matrix-saturation.json --matrix-scorecard reports/qwen-gemma-matrix-scorecard.json --implementation-status reports/implementation-status.json --benchmark-readiness reports/afm-trace-readiness.json --release-provenance reports/release-provenance.json --release-qualification-bundle release-bundles/afm-release.agentblaster-release-qualification.zip --redaction-scan reports/redaction-scan.json --publication-bundle publication-bundles/run.agentblaster-publication.zip --matrix-publication-bundle publication-bundles/qwen-gemma-matrix-summary.agentblaster-matrix-publication.zip --harness-review reports/harness-contract-fuzz-review.json --engine-advisory reports/afm-improvement-plan.json --evidence-index reports/afm-release-evidence-index.json --suite-audit reports/toolsim-suite-audit.json --metric-coverage reports/afm-metric-coverage.json --campaign-preflight-manifest campaign-preflight/qwen-gemma-local/manifest.json --selftest-report test-reports/selftest/selftest-report.json --output-json reports/afm-release-claim-readiness.json
agentblaster release publication-brief --name afm-release --claim-readiness reports/afm-release-claim-readiness.json --matrix-scorecard reports/qwen-gemma-matrix-scorecard.json --release-provenance reports/release-provenance.json --evidence-index reports/afm-release-evidence-index.json --output-json reports/afm-release-publication-brief.json --output-md reports/afm-release-publication-brief.md
agentblaster agents profiles
agentblaster agents suite --profile all --output examples/suites/agentic-local-profiles.yaml
agentblaster agents suite --profile hermes --output examples/suites/agentic-hermes.yaml
agentblaster harness profiles
agentblaster harness generate --profile contract-fuzz --suite smoke --repeats 1 --seed 0 --output examples/suites/harness-contract-fuzz.yaml
agentblaster harness generate --profile metamorphic --suite smoke --repeats 3 --seed 13 --output examples/suites/harness-metamorphic.yaml
agentblaster harness generate --profile cancellation --suite smoke --repeats 3 --seed 23 --output examples/suites/harness-cancellation.yaml
agentblaster harness generate --profile orchestration --suite smoke --repeats 3 --seed 29 --output examples/suites/harness-orchestration.yaml
agentblaster harness generate --profile emerging-workflows --suite smoke --repeats 2 --seed 37 --output examples/suites/harness-emerging-workflows.yaml
agentblaster harness review --suite-file examples/suites/harness-contract-fuzz.yaml --output-json reports/harness-contract-fuzz-review.json
agentblaster models targets
agentblaster models matrix --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suite trace-replay --output examples/matrices/qwen-gemma-local.yaml
agentblaster models stress-matrix --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suites agentic-tool-loop,agent-fanout,prefill,harness-engineering,trace-replay --concurrency-levels 1,2,4,8 --output examples/matrices/qwen-gemma-stress.yaml --summary-json reports/qwen-gemma-stress-plan.json
agentblaster models benchmark-kit --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suite trace-replay --policy agentblaster.policy.yaml --output-dir benchmark-kits/qwen-gemma-local
cat campaigns/qwen-gemma-local/README.md
agentblaster run --matrix examples/matrices/qwen-gemma-local.yaml --offline --continue-on-error --matrix-summary-json reports/qwen-gemma-matrix-summary.json
agentblaster run --matrix examples/matrices/qwen-gemma-stress.yaml --offline --dry-run --plan-json reports/qwen-gemma-stress-plan.json
agentblaster matrix report reports/qwen-gemma-matrix-summary.json --format html,md,json
agentblaster matrix saturation-report reports/qwen-gemma-matrix-summary.json --output-json reports/qwen-gemma-matrix-saturation.json
agentblaster matrix gate reports/qwen-gemma-matrix-summary.json --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95 --max-failure-class engine_protocol_bug=0 --max-tool-loop-stop-reason max_tool_calls_reached=0 --output-json reports/qwen-gemma-matrix-gate.json
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --offline
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --policy agentblaster.policy.yaml
```

Provider profiles are stored locally without raw API keys. API keys can be referenced through environment variables, optional OS keyring storage, or an explicit plaintext `.env` fallback for local development only, with dashboard setup-status posture, provider-audit secret-backend posture, status, test, clear, and writable-secret-delete workflows.

Provider setup details are documented in [docs/providers.md](docs/providers.md), including remote OpenAI/Anthropic presets, the deterministic local mock provider, schema-versioned redacted provider audits, readiness dossiers, portable environment-variable references, optional OS-keyring API-key references, explicit development-only dotenv fallback, cost models for budget policy, and provider rate limits for pacing/concurrency control. Local engine setup recipes are documented in [docs/launch-recipes.md](docs/launch-recipes.md).
Engine target planning includes AFM MLX, MLX-LM, Ollama/Ollama-native, Rapid-MLX, oMLX, vLLM-MLX OpenAI/Anthropic-compatible profiles, LM Studio Chat/Responses/Anthropic/native profiles, and remote OpenAI/Anthropic-compatible contract targets. Each target declares representative agent-profile baselines, workflow surfaces, prefill/concurrency challenges, contract priority, telemetry profiles, and native metric claim policy for standardized comparison.

Reporting details are documented in [docs/reporting.md](docs/reporting.md), including publication JSON plus SVG/PNG report cards for media or corporate consumption. Metric coverage is documented in [docs/metrics.md](docs/metrics.md), including native/measured/inferred/conditional/unavailable field status and stats-semantics guidance for cross-engine comparisons.
Failure classification is documented in [docs/failure-taxonomy.md](docs/failure-taxonomy.md), including the distinction between model-quality misses, engine protocol bugs, feature gaps, runtime failures, environment failures, rate limits, and harness defects.
Artifact schemas are documented in [docs/artifact-schemas.md](docs/artifact-schemas.md), including publication-safety guidance for run, matrix, lifecycle, raw, and readiness artifacts.

Reproducibility details are documented in [docs/reproducibility.md](docs/reproducibility.md), including suite snapshots, suite/case hashes, run integrity manifests, signatures, and publication-bundle signature coverage metadata.
Implementation status inventory is available through `agentblaster implementation-status`; it is a static handoff artifact and does not run tests or contact providers. It reports file presence plus static requirement inventories for target engines, engine-target standardization metadata, provider contracts, Qwen/Gemma model targets, agent profiles, built-in harness-engineering suite cases, stats-comparability/metric-coverage catalogs, enterprise policy controls, credential/backend posture including optional keyring support, run/matrix publication-bundle governance with media-kit manifests, and SDLC/Chrome self-test gates.
Retention metadata is documented in [docs/retention.md](docs/retention.md), including manifest fields for artifact classification, intended run retention, and shorter raw-trace retention.

Observability details are documented in [docs/observability.md](docs/observability.md), including optional Prometheus before/after snapshots for local engine telemetry and normalized response telemetry with comparison-readiness metadata. Agent fan-out diagnostics are documented in [docs/agent-fanout.md](docs/agent-fanout.md). Cache-control diagnostics are documented in [docs/cache-control.md](docs/cache-control.md). Cancellation diagnostics are documented in [docs/cancellation.md](docs/cancellation.md). The built-in `agentic-tool-loop` suite exercises bounded deterministic tool-result replay, MCP fixture calls, LCP context attachment, and max-tool-call stop-reason reporting.

Dashboard details are documented in [docs/dashboard.md](docs/dashboard.md), including the no-JavaScript launch/report-generation forms and allowlisted report artifact links.

Capability preflight is documented in [docs/capabilities.md](docs/capabilities.md), including suite feature requirements and provider-suite compatibility checks.
Run execution performs capability preflight by default, failing before dispatch when a provider is explicitly missing suite-required features.
Bundled capability surface catalogs are documented in [docs/capability-surfaces.md](docs/capability-surfaces.md), including simulated tool, deterministic MCP profile, LCP context-bundle, and skill-pack inventory commands for policy review.
Suite governance is documented in [docs/suite-governance.md](docs/suite-governance.md), including static provenance, risk, license/source, and capability-surface audits before dispatch.
Evidence bundles are documented in [docs/evidence-bundles.md](docs/evidence-bundles.md), including redaction-safe governance zip artifacts for corporate review and media-supporting benchmark evidence.
Campaign preflight bundles are also documented there; they collect no-dispatch readiness, schema, policy, provider-audit, and matrix-inventory artifacts before expensive local or remote matrices are launched.

Model targets, matrix generation, and benchmark kits are documented in [docs/models.md](docs/models.md), including the initial Qwen3.6 27B dense and Gemma 4 31B dense comparison targets, comparison-group guidance, required release metadata, and provider contract-matrix commands for campaign compatibility evidence.
The checked-in Qwen/Gemma campaign handoff lives in [campaigns/qwen-gemma-local/README.md](campaigns/qwen-gemma-local/README.md).

Dry-run planning is documented in [docs/planning.md](docs/planning.md), including policy/capability preflight and estimated token/cost summaries before dispatch. Prompt footprint analysis is documented in [docs/prompt-footprint.md](docs/prompt-footprint.md), including system/tool/MCP/LCP/skill prefix breakdowns for prefill diagnostics. Matrix pressure audits extend that analysis across provider/model/suite/concurrency matrices before dispatch.

Run execution includes enterprise controls: raw traces can be disabled, remote providers can be blocked with `--offline`, YAML policy files can allowlist providers and endpoint hosts, policy can require remote API-key references, policy can restrict secret backends and approved secret reference names/prefixes, policy can require cleanup audit logs, policy can cap suite and matrix cost exposure, policy can gate suite-provided tool schemas, simulated tools, MCP profiles, LCP context bundles, skills, provenance, risk levels, and source/license metadata, and optional JSONL audit logs record run and policy events.
Security policy details are documented in [docs/security-policy.md](docs/security-policy.md), including enterprise baseline generation with `agentblaster policy template`, no-secret review summaries with `agentblaster policy controls`, and `agentblaster.provider-audit.v1` provider/auth posture audits. The example policy in [agentblaster.policy.example.yaml](agentblaster.policy.example.yaml) separates provider endpoint allowlists from Prometheus metrics endpoint allowlists and includes capability-surface allowlists.

Audit logging details are documented in [docs/audit.md](docs/audit.md), including control-plane events for provider config, secret reference changes, dashboard start, report generation, matrix reports, and exports.

AgentBlaster includes its own SDLC test harness taxonomy. The `quality` commands describe deterministic app-test tiers, release lanes, SDLC validation manifests, Chrome/Codex dashboard validation plans, and redacted dashboard fixtures with release-evidence summaries, including bounded `agentic-tool-loop` stop-reason gate metadata, without running tests. SDLC validation manifests are direct review artifacts and can also be archived through release qualification bundles as compact summaries for claim-readiness, evidence-index, and dashboard review.
Experiment manifests are documented in [docs/experiments.md](docs/experiments.md), including static scope, preflight requirements, acceptance gates, and publication rules for corporate/media benchmark campaigns. Release governance artifacts can be generated with `agentblaster release packaging-readiness` and `agentblaster release provenance`; the JSON outputs record package metadata readiness, dependency declarations, an SPDX-lite SBOM inventory, optional installed package inventory, safe source hashes, and explicit redaction notes. Release qualification bundles collect evidence, audit, advisory, gate, readiness, provenance, publication, SDLC validation, and selftest artifacts into one checksum-indexed package. Provider audits, publication briefs, and SDLC validation manifests are summarized, not copied verbatim, for release qualification, claim-readiness, evidence-index, and dashboard consumers; publication briefs also surface compact engine-target IDs and media-kit readiness from compact claim-readiness evidence without opening publication ZIP bundles. Generated campaign runbooks include claim-readiness, publication-brief, and final archival bundle commands so corporate/media packets can carry the final claim gate, brief, provider-auth posture, media-kit readiness, and app-SDLC review evidence in compact redaction-safe form. Use `agentblaster security scan` as a final local redaction gate before publishing bundles; it scans text files, text entries inside ZIP bundles, and unsafe ZIP member names without extracting archives or printing matched secret/local-path values.
Repository automation is documented in [docs/testing.md](docs/testing.md), including deterministic CI and a safe package-build workflow that uploads artifacts without publishing to PyPI.

AgentBlaster includes representative local-agent profile generators for OpenCode-style, OpenClaw-style, Nous Hermes-style, Pi-style, Aider-style, Cline-style, Continue-style, and Codex-style workflows. The `agents` commands write reviewable YAML suites with tool, MCP, LCP, skill, trace-replay, structured-output, retrieval, and sandboxed command-planning surfaces and do not call providers or install third-party agent frameworks.

AgentBlaster also includes deterministic harness-engineering generators for prefill/cache, concurrency, cancellation, provider-contract fuzz, metamorphic-equivalence, skill-prefix routing, multi-tool orchestration, mixed emerging MCP/LCP/skills/tool-loop stacks, and judge-rubric workloads with bounded fixture tool-result round trips. The `harness` commands write reviewable YAML suites and static harness-review artifacts without calling providers.
Harness engineering details are documented in [docs/harness.md](docs/harness.md), including generated-suite provenance and reporting metadata.

Trace replay cases can provide explicit `messages` for multi-turn agent workflows, including prior assistant tool calls and deterministic tool-result context. OpenAI-compatible and Anthropic-compatible adapters normalize those traces into their respective request contracts.

## Planned Benchmark CLI

```bash
agentblaster report runs/<run-id> --format html
```
