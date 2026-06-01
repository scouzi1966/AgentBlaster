# AgentBlaster SDLC Test Harness

AgentBlaster has two distinct testing layers:

- App tests verify AgentBlaster itself: schemas, adapters, policy, storage, CLI, dashboard, reports, exports, packaging, and security controls.
- Benchmark suites verify inference engines and models under agentic workloads.

Do not mix app test failures into engine benchmark scores. If the harness is wrong, classify the issue as a harness defect and fix AgentBlaster first.

## Test Tiers

Use pytest markers to keep local, CI, GUI, remote, and hardware-specific work separate.

| Marker | Purpose | Default CI |
| --- | --- | --- |
| `unit` | Pure, fast tests for schemas, normalizers, policy, scoring, and redaction helpers. | Yes |
| `contract` | Mocked OpenAI, Anthropic, and native engine response-shape tests. | Yes |
| `integration` | Local CLI, storage, artifact, report, export, and dashboard HTTP behavior. | Yes |
| `security` | Secret handling, redaction, dashboard bind policy, trace policy, and allowlist checks. | Yes |
| `gui` | Browser-driven dashboard tests with deterministic fixture data. | Optional |
| `remote` | Opt-in internet-facing provider tests requiring API keys. | No |
| `slow` | Long-running, hardware-specific, or large-fixture tests. | No |
| `packaging` | Wheel, source distribution, optional extras, and CLI entrypoint validation. | Release |

Recommended local commands:

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src pytest -q -m "security or contract"
PYTHONPATH=src pytest -q -m "not remote and not slow"
agentblaster verify runs/<run-id>
agentblaster bundle runs/<run-id> --output-dir bundles/
```

AgentBlaster also exposes its app-test taxonomy through the CLI:

```bash
agentblaster quality tiers
agentblaster quality command normal
agentblaster quality command security
agentblaster quality command gui
agentblaster quality gates --format json --output test-reports/sdlc-gates.json
agentblaster quality gates --format markdown --output test-reports/sdlc-gates.md
agentblaster quality validation-manifest --format json --output test-reports/sdlc-validation-manifest.json
agentblaster quality validation-manifest --format markdown --output test-reports/sdlc-validation-manifest.md
agentblaster quality chrome-checklist --output tests/gui/chrome-dashboard-checklist.md
agentblaster quality chrome-plan --format json --output tests/gui/chrome-dashboard-plan.json
agentblaster quality gui-spec --format json --output tests/gui/gui-test-spec.json
agentblaster quality gui-artifacts --output tests/gui --overwrite
agentblaster quality dashboard-fixture --output tests/fixtures/dashboard-runs --overwrite
agentblaster doctor --output-json reports/environment-readiness.json
agentblaster implementation-status --output-json reports/implementation-status.json
agentblaster mock-provider --host 127.0.0.1 --port 8787
agentblaster providers contract-check --provider mock-openai --model agentblaster-mock-qwen3.6-27b-dense --execute
```

The executable selftest harness uses the same tiers:

```bash
agentblaster doctor --output-json reports/environment-readiness.json --fail-on-required-gaps
agentblaster selftest --tier fast --dry-run
agentblaster selftest --tier normal --report-dir test-reports/selftest --junit-xml test-reports/selftest/normal.junit.xml
agentblaster selftest gui --browser chromium --headed --dry-run
PYTHONPATH=src pytest -q tests/gui -m gui
agentblaster selftest report --run selftest_20260531T000000Z --format html,json,junit
agentblaster release packaging-readiness --output-json reports/packaging-readiness.json --fail-on-gaps
agentblaster release provenance --output reports/release-provenance.json
```

Use `--dry-run` when reviewing the planned command without executing tests. Use `--report-dir` for recorded selftest execution metadata that can be converted into HTML, JSON, or JUnit summary artifacts. JSON selftest reports use `agentblaster.selftest-report.v1`; release and claim-readiness summaries copy only compact status metadata, not command strings, environment maps, or raw test output. Use `agentblaster quality gates` to generate the SDLC gate catalog that maps local, pre-merge, nightly, release, security, GUI, remote, and hardware-dependent checks to commands, blocking policy, and release evidence, including bounded `agentic-tool-loop` stop-reason gate summaries from matrix-gate artifacts. Use `agentblaster quality validation-manifest` to create `agentblaster.sdlc-validation-manifest.v1`, a static no-execution manifest that ties tiers, gates, Chrome/Codex GUI hooks, fixture commands, stable selectors, API surfaces, and expected release evidence into one reviewable artifact.
Use `--run-id <id>` with `agentblaster selftest` or `agentblaster selftest gui` when release evidence needs deterministic paths, then run `agentblaster selftest report --run <id> --base-dir <report-dir> --format html,json,junit` to create the JSON report consumed by release qualification and claim readiness.

`agentblaster doctor` is a static readiness check. It reports Python/platform metadata, required runtime dependency importability, optional keyring/GUI/packaging/selftest dependency availability, and AgentBlaster config paths. It does not contact providers, resolve API keys, inspect keyring values, or read provider config contents.

`agentblaster implementation-status` is a static implementation inventory. It checks whether expected source, docs, workflow, and test surfaces are present, lists built-in suites, and records that validation still must be run separately. It also publishes static requirement inventories for target engines, engine-target standardization metadata, provider contracts, Qwen/Gemma model targets, model comparison groups, required release metadata, agent profiles, built-in harness-engineering suite cases, stats-comparability/metric-coverage catalogs, enterprise policy controls, publication-bundle governance, and SDLC/Chrome self-test gates. Use it as a handoff artifact before the explicit validation/fix pass.

The implementation inventory also declares `agentblaster.selftest-report.v1` as the SDLC evidence schema and records which compact fields may flow into release qualification, claim readiness, dashboard review artifacts, evidence indexes, artifact-schema registries, selftest report summaries, and benchmark readiness summaries. Command strings, environment maps, raw test output, raw provider configs, and API-key material are explicitly excluded from release summaries.

Remote-provider tests must be skipped unless the required credentials are explicitly configured through environment variables or a secure OS keyring reference. Use `agentblaster mock-provider --host 127.0.0.1 --port 8787` for deterministic OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, model-list, streaming, tool-call, auth-denial, and metrics contract checks without live engines or paid APIs.

## Repository Automation

`.github/workflows/ci.yml` runs deterministic app tests across Ubuntu, macOS, Windows, Python 3.11, and Python 3.12. It also generates static environment readiness, packaging readiness, release provenance, provider governance, dashboard GUI-plan, and redaction-scan artifacts without contacting remote providers.

`.github/workflows/publish.yml` is a safe package-build workflow for tags and manual dispatch. It builds source and wheel distributions, scans release artifacts, and uploads GitHub Actions artifacts. It does not publish to PyPI.

## GUI Testing

The dashboard is intentionally served on loopback by default:

```bash
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765
```

GUI tests should use deterministic fixture run directories and redacted data. They must not depend on raw provider traces, local browser history, real API keys, or live paid provider calls. Generate safe dashboard fixtures with `agentblaster quality dashboard-fixture --output tests/fixtures/dashboard-runs --overwrite`. The generated fixture directory includes redacted run folders, a `campaign-preflight/` manifest with compact no-local-path `review_summary`, a campaign-preflight benchmark-readiness index with compact provider/suite/model/auth-posture readiness metadata, and a `release-bundles/` fixture containing compact matrix-gate failure-class and tool-loop stop-reason metadata, provider-contract capability evidence, implementation-status readiness metadata, campaign-preflight planning metadata, harness-review calibration metadata, engine-advisory priority metadata, evidence-index readiness metadata, suite-audit dataset-hygiene metadata, and metric-coverage comparability metadata for the Review evidence panel.

Preferred automation lanes:

- Playwright for deterministic CI GUI tests.
- Chrome/Codex plugin-assisted validation for interactive desktop checks, authenticated/profile-dependent browser scenarios, extension interactions, and exploratory review.

Chrome/Codex plugin validation should complement CI. It is not a replacement for repeatable Playwright-style checks. Use `agentblaster quality chrome-plan` to generate a deterministic JSON or Markdown plan that maps dashboard flows to Chrome/Codex steps, expected results, selectors, API surfaces, and evidence requirements. The dashboard planning catalog panel exposes read-only links for model targets, engine targets, local-engine onboarding, workflow surfaces, telemetry mappings, providers, suites, and a campaign preview so Chrome/Codex GUI validation can inspect setup metadata without launching runs.

Dashboard launch review should call `POST /api/run-plan` before `POST /api/runs` when collecting GUI evidence. The run-plan preview must return a redacted dry-run plan and safety flags without contacting a provider, resolving a secret, or writing run artifacts.

The repo includes a deterministic GUI lane under `tests/gui/`. These tests use seeded dashboard run fixtures and release-evidence fixtures, start the dashboard on loopback, and skip cleanly when Playwright/browser dependencies are not installed. Run them with `PYTHONPATH=src pytest -q tests/gui -m gui` or through `agentblaster selftest gui` once browser dependencies are installed. The Chrome validation checklist lives at `tests/gui/chrome-dashboard-checklist.md` and can be regenerated with `agentblaster quality chrome-checklist`. The structured Chrome/Codex plan should be stored as `tests/gui/chrome-dashboard-plan.json` for release-evidence review when GUI validation is performed manually or semi-automatically. The unified GUI self-test specification is generated with `agentblaster quality gui-spec` or `agentblaster quality gui-artifacts`; it binds the fixture lane, CI Playwright lane, Chrome/Codex evidence lane, and release evidence requirements into one deterministic artifact set.

Dashboard selectors intended for GUI automation:

- `data-testid="launch-panel"`
- `data-testid="launch-form"`
- `data-testid="provider-select"`
- `data-testid="suite-select"`
- `data-testid="model-input"`
- `data-testid="run-plan-submit"`
- `data-testid="run-plan-panel"`
- `data-testid="run-plan-safety"`
- `data-testid="run-plan-cases-table"`
- `data-testid="launch-submit"`
- `data-testid="provider-setup-panel"`
- `data-testid="provider-setup-form"`
- `data-testid="provider-setup-name-input"`
- `data-testid="provider-setup-contract-select"`
- `data-testid="provider-setup-base-url-input"`
- `data-testid="provider-setup-model-input"`
- `data-testid="provider-setup-api-key-env-input"`
- `data-testid="provider-setup-remote-input"`
- `data-testid="provider-setup-submit"`
- `data-testid="provider-auth-panel"`
- `data-testid="provider-auth-form"`
- `data-testid="provider-auth-select"`
- `data-testid="provider-auth-method-select"`
- `data-testid="provider-auth-env-input"`
- `data-testid="provider-auth-api-key-input"`
- `data-testid="provider-auth-submit"`
- `data-testid="catalog-panel"`
- `data-testid="catalog-link"`
- `data-testid="review-artifacts-panel"`
- `data-testid="review-artifacts-table"`
- `data-testid="review-artifact-link"`
- `data-testid="runs-panel"`
- `data-testid="runs-table"`
- `data-testid="run-row"`
- `data-testid="report-artifact-link"`
- `data-testid="empty-state"`

Dashboard API surfaces intended for GUI automation:

- `GET /api/providers` returns redacted configured provider profiles.
- `GET /api/setup-status` returns static redacted provider setup status, policy/auth/TLS findings, and readiness warnings without resolving secrets or contacting endpoints.
- `POST /api/providers` creates or updates a provider profile using endpoint metadata and optional `env:` secret references only.
- `POST /providers` supports the no-JavaScript dashboard provider setup form with the same redaction and audit guarantees.
- `POST /api/providers/<provider>/auth` stores an env, optional keyring/Keychain, or explicit plaintext dotenv API-key reference without echoing the submitted value, and writes a redacted audit event when dashboard audit logging is enabled.
- `DELETE /api/providers/<provider>/auth?delete_secret=true` clears provider auth references and deletes only writable keyring/dotenv-backed secrets; environment-variable secret deletion remains external to AgentBlaster.
- `POST /providers/auth` supports the no-JavaScript dashboard auth setup form with the same redaction and audit guarantees.
- `GET /api/suites` returns built-in suite metadata and case summaries.
- `GET /api/models` returns canonical Qwen/Gemma model targets for matrix planning.
- `GET /api/engine-targets` returns standardized engine target planning metadata.
- `GET /api/local-engine-onboarding` returns static local-engine preset, launch recipe, engine target, workflow-surface, and telemetry-policy setup metadata.
- `GET /api/workflow-surfaces` returns tool, MCP, skill, LCP, and harness-engineering surface metadata.
- `GET /api/telemetry-mappings` returns raw-to-normalized telemetry mapping metadata.
- `GET /api/catalogs` returns the read-only dashboard catalog index.
- `GET /api/campaign-preview` returns a no-write canonical campaign plan preview for GUI setup review.
- `GET /api/review-artifacts` returns a redaction-safe evidence index, including compact campaign-preflight manifest, release qualification matrix-gate failure-class, tool-loop stop-reason, implementation-status, and metric-coverage comparability summaries when present.
- `GET /api/review-artifacts/<path>` returns a defensively redacted detail view for small JSON review artifacts and continues to block raw paths, `results.jsonl`, and zip bundle detail views.
- `POST /api/run-plan` returns a no-dispatch benchmark preview that enforces launch policy, estimates prompt/output/cost shape, and reports capability preflight findings when requested.
- `POST /run-plan` supports the no-JavaScript dashboard run-plan preview page with the same no-dispatch safety contract.
- `GET /api/runs` lists completed run summaries.
- `GET /api/runs/<run-id>` returns manifest, summary, and normalized result rows.
- `GET /api/runs/<run-id>/events` returns redacted lifecycle events from `events.jsonl`.
- `POST /api/runs` launches a built-in suite against a configured local provider by default; remote providers require explicit `allow_remote: true`.
- `POST /launch` launches a built-in suite from the no-JavaScript dashboard form.
- `GET /runs/<run-id>/artifacts/<artifact>` serves allowlisted report artifacts only.

## Security Expectations

Security tests must verify these invariants:

- Raw API keys never appear in provider config, manifests, reports, exports, dashboard HTML, dashboard JSON, logs, screenshots, or raw trace artifacts.
- Dashboard setup status is static and must not contact endpoints, resolve API keys, read environment variables, or inspect keyring values.
- Dashboard run-plan preview must not contact endpoints, resolve API keys, read environment variables, inspect keyring values, or create run artifacts.
- Dashboard provider setup stores endpoint metadata and optional `env:` secret references only; raw API-key values are rejected by provider config validation.
- Dashboard provider-auth setup stores only `SecretRef` metadata in provider config; env mode is portable and keyring mode depends on the optional OS credential backend such as Apple Keychain on macOS.
- Dashboard provider-auth setup writes `provider_auth_ref_changed` audit events when `--audit-log` is configured, without recording submitted API-key values.
- Run manifests capture reproducibility metadata without storing raw hostnames or other unnecessary host identifiers.
- Completed runs include `integrity.json` with SHA-256 checksums for manifests, results, summaries, and raw artifacts when raw capture is enabled.
- Provider config files are written with owner-only permissions where the platform supports POSIX modes.
- The dashboard refuses non-loopback binds unless the operator explicitly opts in.
- Raw trace capture defaults to redacted mode and can be disabled.
- Full raw trace mode requires policy permission.
- Remote providers are blocked in offline mode.
- Enterprise policy ceilings can block suites before execution based on case count, output tokens, timeout, estimated prompt size, and estimated provider cost.
- Enterprise policy ceilings can block whole matrices before execution based on run count, total resolved case count, and aggregate estimated cost.
- Enterprise policy can block or allowlist suite-provided tool schemas, deterministic simulated tools, MCP profiles, and skill packs before provider dispatch.
- Generated harness suites should produce `agentblaster harness review --suite-file <suite.yaml> --output-json reports/<suite>-harness-review.json` before dispatch so reviewers can approve generated-suite provenance, capability surfaces, assertions, metrics, risk signals, and calibration requirements without reading prompts or raw provider payloads.
- Enterprise policy can require tool-surface cases to declare `max_tool_calls` and cap the declared deterministic tool-loop depth before dispatch.
- Enterprise policy can block high-risk cases and require source/license metadata for externally derived suites before dispatch.
- Provider `rate_limits` can enforce max concurrency and pace requests before dispatch so remote benchmark runs do not create accidental bursts.

## Packaging And Release Validation

Every tagged release should produce a reproducible test report containing:

- Python version and platform matrix.
- App test marker summary.
- Packaging validation output.
- Static packaging readiness output from `agentblaster release packaging-readiness`.
- Optional `agentblaster compare-gate` output for AFM baseline-vs-candidate regression thresholds.
- Optional `agentblaster matrix gate reports/qwen-gemma-matrix-summary.json --require-all-runs-complete --max-failed-runs 0 --min-case-pass-rate 95 --max-failure-class engine_protocol_bug=0 --max-tool-loop-stop-reason max_tool_calls_reached=0 --min-judge-verdict-valid-rate 95 --include-tool-loop-summary --include-judge-verdict-summary --output-json reports/qwen-gemma-matrix-gate.json` output for provider/model matrix release thresholds, class-specific publication blockers, bounded `agentic-tool-loop` stop-reason blockers, and judge-rubric validity blockers.
- Release qualification bundle from `agentblaster release qualification-bundle`.
- Redaction scan output from `agentblaster security scan` for shareable bundles.
- Release provenance JSON from `agentblaster release provenance`.
- Security test result summary.
- Dashboard fixture validation result.
- Any skipped remote or hardware-specific tests with explicit reasons.

The release provenance artifact is a lightweight SBOM-style JSON file. It records project metadata, declared runtime and optional dependencies, build-system requirements, optional installed package names and versions, selected safe source-file hashes, packaging readiness, and redaction notes. It does not read environment variables, provider configs, run traces, raw responses, or dashboard state.
