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
agentblaster quality chrome-checklist --output tests/gui/chrome-dashboard-checklist.md
agentblaster quality chrome-plan --format json --output tests/gui/chrome-dashboard-plan.json
agentblaster quality gui-spec --format json --output tests/gui/gui-test-spec.json
agentblaster quality gui-artifacts --output tests/gui --overwrite
agentblaster quality dashboard-fixture --output tests/fixtures/dashboard-runs --overwrite
agentblaster mock-provider --host 127.0.0.1 --port 8787
agentblaster providers contract-check --provider mock-openai --model agentblaster-mock-qwen3.6-27b-dense --execute
```

The executable selftest harness uses the same tiers:

```bash
agentblaster selftest --tier fast --dry-run
agentblaster selftest --tier normal --report-dir test-reports/selftest --junit-xml test-reports/selftest/normal.junit.xml
agentblaster selftest gui --browser chromium --headed --dry-run
PYTHONPATH=src pytest -q tests/gui -m gui
agentblaster selftest report --run selftest_20260531T000000Z --format html,json,junit
agentblaster release provenance --output reports/release-provenance.json
```

Use `--dry-run` when reviewing the planned command without executing tests. Use `--report-dir` for recorded selftest execution metadata that can be converted into HTML, JSON, or JUnit summary artifacts. Use `agentblaster quality gates` to generate the SDLC gate catalog that maps local, pre-merge, nightly, release, security, GUI, remote, and hardware-dependent checks to commands, blocking policy, and release evidence.

Remote-provider tests must be skipped unless the required credentials are explicitly configured through environment variables or a secure OS keyring reference. Use `agentblaster mock-provider --host 127.0.0.1 --port 8787` for deterministic OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, model-list, streaming, tool-call, auth-denial, and metrics contract checks without live engines or paid APIs.

## GUI Testing

The dashboard is intentionally served on loopback by default:

```bash
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765
```

GUI tests should use deterministic fixture run directories and redacted data. They must not depend on raw provider traces, local browser history, real API keys, or live paid provider calls. Generate safe dashboard fixtures with `agentblaster quality dashboard-fixture --output tests/fixtures/dashboard-runs --overwrite`.

Preferred automation lanes:

- Playwright for deterministic CI GUI tests.
- Chrome/Codex plugin-assisted validation for interactive desktop checks, authenticated/profile-dependent browser scenarios, extension interactions, and exploratory review.

Chrome/Codex plugin validation should complement CI. It is not a replacement for repeatable Playwright-style checks. Use `agentblaster quality chrome-plan` to generate a deterministic JSON or Markdown plan that maps dashboard flows to Chrome/Codex steps, expected results, selectors, API surfaces, and evidence requirements. The dashboard planning catalog panel exposes read-only links for model targets, engine targets, workflow surfaces, telemetry mappings, providers, suites, and a campaign preview so Chrome/Codex GUI validation can inspect setup metadata without launching runs.

The repo includes a deterministic GUI lane under `tests/gui/`. These tests use seeded dashboard run fixtures, start the dashboard on loopback, and skip cleanly when Playwright/browser dependencies are not installed. Run them with `PYTHONPATH=src pytest -q tests/gui -m gui` or through `agentblaster selftest gui` once browser dependencies are installed. The Chrome validation checklist lives at `tests/gui/chrome-dashboard-checklist.md` and can be regenerated with `agentblaster quality chrome-checklist`. The structured Chrome/Codex plan should be stored as `tests/gui/chrome-dashboard-plan.json` for release-evidence review when GUI validation is performed manually or semi-automatically. The unified GUI self-test specification is generated with `agentblaster quality gui-spec` or `agentblaster quality gui-artifacts`; it binds the fixture lane, CI Playwright lane, Chrome/Codex evidence lane, and release evidence requirements into one deterministic artifact set.

Dashboard selectors intended for GUI automation:

- `data-testid="launch-panel"`
- `data-testid="launch-form"`
- `data-testid="provider-select"`
- `data-testid="suite-select"`
- `data-testid="model-input"`
- `data-testid="launch-submit"`
- `data-testid="catalog-panel"`
- `data-testid="catalog-link"`
- `data-testid="runs-panel"`
- `data-testid="runs-table"`
- `data-testid="run-row"`
- `data-testid="report-artifact-link"`
- `data-testid="empty-state"`

Dashboard API surfaces intended for GUI automation:

- `GET /api/providers` returns redacted configured provider profiles.
- `GET /api/suites` returns built-in suite metadata and case summaries.
- `GET /api/models` returns canonical Qwen/Gemma model targets for matrix planning.
- `GET /api/engine-targets` returns standardized engine target planning metadata.
- `GET /api/workflow-surfaces` returns tool, MCP, skill, LCP, and harness-engineering surface metadata.
- `GET /api/telemetry-mappings` returns raw-to-normalized telemetry mapping metadata.
- `GET /api/catalogs` returns the read-only dashboard catalog index.
- `GET /api/campaign-preview` returns a no-write canonical campaign plan preview for GUI setup review.
- `GET /api/runs` lists completed run summaries.
- `GET /api/runs/<run-id>` returns manifest, summary, and normalized result rows.
- `POST /api/runs` launches a built-in suite against a configured local provider by default; remote providers require explicit `allow_remote: true`.
- `POST /launch` launches a built-in suite from the no-JavaScript dashboard form.
- `GET /runs/<run-id>/artifacts/<artifact>` serves allowlisted report artifacts only.

## Security Expectations

Security tests must verify these invariants:

- Raw API keys never appear in provider config, manifests, reports, exports, dashboard HTML, dashboard JSON, logs, screenshots, or raw trace artifacts.
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
- Enterprise policy can require tool-surface cases to declare `max_tool_calls` and cap the declared tool-loop depth before dispatch.
- Enterprise policy can block high-risk cases and require source/license metadata for externally derived suites before dispatch.
- Provider `rate_limits` can enforce max concurrency and pace requests before dispatch so remote benchmark runs do not create accidental bursts.

## Packaging And Release Validation

Every tagged release should produce a reproducible test report containing:

- Python version and platform matrix.
- App test marker summary.
- Packaging validation output.
- Optional `agentblaster compare-gate` output for AFM baseline-vs-candidate regression thresholds.
- Optional `agentblaster matrix gate` output for provider/model matrix release thresholds.
- Release qualification bundle from `agentblaster release qualification-bundle`.
- Redaction scan output from `agentblaster security scan` for shareable bundles.
- Release provenance JSON from `agentblaster release provenance`.
- Security test result summary.
- Dashboard fixture validation result.
- Any skipped remote or hardware-specific tests with explicit reasons.

The release provenance artifact is a lightweight SBOM-style JSON file. It records project metadata, declared runtime and optional dependencies, build-system requirements, optional installed package names and versions, selected safe source-file hashes, and redaction notes. It does not read environment variables, provider configs, run traces, raw responses, or dashboard state.
