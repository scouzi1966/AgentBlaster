# AgentBlaster Dashboard

The dashboard is an optional browser surface over the same provider registry, suite registry, and run artifacts used by the CLI.

Start it on loopback:

```bash
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765
```

Enable token authentication:

```bash
export AGENTBLASTER_DASHBOARD_TOKEN="$(openssl rand -hex 32)"
agentblaster dashboard \
  --runs runs \
  --host 127.0.0.1 \
  --port 8765 \
  --policy agentblaster.policy.yaml \
  --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN
```

Bind beyond loopback only with explicit opt-in and token authentication:

```bash
agentblaster dashboard \
  --runs runs \
  --host 0.0.0.0 \
  --port 8765 \
  --policy agentblaster.policy.yaml \
  --allow-non-loopback \
  --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN
```

## Capabilities

- Browse completed run summaries.
- View suite hash and provenance metadata for reproducibility checks.
- Open safe metrics summary artifacts when Prometheus snapshots are configured.
- Inspect redacted provider and suite metadata through API endpoints.
- Inspect a redaction-safe index of static evidence, provider contract matrices, saturation reports, gates, audits, advisories, harness reviews, claim-readiness, run publication bundles, matrix publication bundles, and release artifacts.
- Configure provider profiles and auth references through redacted dashboard forms or APIs.
- Preview benchmark launch policy, cost, case, capability compatibility, and per-case capability surfaces through a no-dispatch run plan API.
- Launch built-in suites against configured providers from a no-JavaScript HTML form.
- Launch API responses include a versioned safety envelope that states provider requests were dispatched, run artifacts were written, policy was enforced, and capability preflight was applied.
- Generate report artifacts for completed runs from the browser or API.
- Keep remote providers blocked by default unless the operator explicitly checks `allow remote provider`.
- Open generated report artifacts through allowlisted links.
- Show a visible security posture panel for dashboard auth, configured remote providers, insecure TLS providers, full raw trace runs, and allowlisted artifact serving.

## Browser Routes

- `/`: dashboard HTML.
- `/login`: no-JavaScript token login form when dashboard auth is enabled.
- `/logout`: clears the dashboard auth cookie.
- `/providers`: server-side form endpoint for provider profile setup.
- `/providers/auth`: server-side form endpoint for provider auth-reference setup.
- `/providers/auth/clear`: server-side form endpoint for clearing provider auth references, with optional writable keyring/dotenv secret deletion.
- `/run-plan`: server-side form endpoint for rendering a no-dispatch run-plan preview.
- `/launch`: server-side form endpoint for launching a run.
- `/runs/<run-id>/reports`: server-side form endpoint for generating reports.
- `/api/providers`: redacted provider registry and JSON provider setup endpoint. Setup responses include a static `policy_review` block when the dashboard was started with `--policy`.
- `/api/setup-status`: static redacted provider setup, auth, auth-setup posture, secret-backend posture, TLS, and policy readiness summary using the configured dashboard policy when one is supplied.
- `/api/engine-targets`: static engine target catalog, including primary scoring contracts, contract priority, telemetry profiles, workflow surfaces, representative agent profiles, prefill/concurrency challenge classes, and native metric claim policy.
- `/api/local-engine-onboarding`: static local-engine onboarding checklist joining provider presets, launch recipes, engine targets, workflow surfaces, and native metric policy without launching engines or reading secrets.
- `/api/providers/<provider>/auth`: JSON provider auth-reference setup endpoint on `POST`; auth-reference clear endpoint on `DELETE`, with `?delete_secret=true` for writable keyring/dotenv secret deletion. Auth responses include static `policy_review` metadata when a dashboard policy is configured.
- `/api/run-plan`: JSON no-dispatch benchmark preview endpoint that enforces launch policy before execution.
- `/api/review-artifacts`: redaction-safe metadata index for static review artifacts in `reports`, `evidence`, `publication-bundles`, `release-bundles`, and `campaign-preflight`.
- `/api/review-artifacts/<path>`: redacted detail view for one small JSON review artifact from the index.
- `/api/suites`: built-in suite metadata.
- `/api/telemetry-mappings`: static raw-to-normalized telemetry mapping catalog, including `stats_comparability` guidance for cross-engine publication claims.
- `/api/runs`: completed run summaries on `GET`; policy-gated benchmark launch on `POST`.
- `/api/runs/<run-id>`: manifest, summary, and normalized results.
- `/api/runs/<run-id>/events`: redacted lifecycle event timeline from `events.jsonl`.
- `/api/runs/<run-id>/reports`: JSON endpoint for generating report artifacts.
- `/runs/<run-id>/artifacts/<artifact>`: allowlisted report artifact serving.

Allowed artifact names:

- `report.html`
- `report.md`
- `report.pdf`
- `summary.json`
- `publication.json`
- `report-card.svg`
- `metrics/prometheus-summary.json`

## Security Posture

- The dashboard binds to loopback by default.
- Non-loopback binding requires explicit CLI opt-in and token authentication.
- Policy files can restrict dashboard hosts and ports, require dashboard auth even on loopback, and disable or explicitly allow non-loopback binding.
- Non-loopback startup must satisfy both the policy file and CLI safety checks: `allow_dashboard_non_loopback: true`, `--allow-non-loopback`, and `--auth-token-env`.
- Token authentication can use a browser login cookie or `Authorization: Bearer <token>` for API clients.
- Dashboard tokens are read from an environment variable and are never written to provider config, run artifacts, reports, or cookies.
- Dashboard tokens must be at least 16 characters; use a high-entropy value from an enterprise secret manager or OS-protected shell environment.
- The auth cookie stores a SHA-256 token digest, not the raw token, and is marked `HttpOnly` and `SameSite=Strict`.
- CSP disables scripts and restricts form submission to same-origin.
- Artifact serving is allowlisted and does not expose raw traces or manifests.
- Report generation reads existing run artifacts and writes only allowlisted report formats.
- Raw Prometheus before/after text is not served by the dashboard; only the derived metrics summary JSON is allowlisted.
- Setup status is static and does not contact endpoints, resolve API keys, inspect keyring values, or read dotenv secret files. Its `auth_setup` and `secret_backend_posture` blocks report env/keyring/dotenv availability, optional keyring dependency availability, policy allowance, raw-key-entry behavior, plaintext fallback status, and enterprise recommendation without testing or reading any secret value.
- Provider setup/auth responses include static policy review metadata when `agentblaster dashboard --policy ...` is used. These reviews reuse provider policy checks, report pass/block status and sanitized findings, and do not contact provider endpoints or resolve secret values. Setup status also exposes static policy-control posture such as whether cleanup audit logs are required by policy.
- Run-plan preview is available through both `/run-plan` and `/api/run-plan`; it enforces launch policy and optional capability preflight without contacting provider endpoints, resolving secrets, or writing run artifacts. The safety envelope includes compatibility state plus missing and unknown capability keys, while the rendered HTML case table shows capability surfaces such as `structured_output`, `judge_rubric`, `prompt_caching`, `tool_loop`, or `cancellation` plus static/dynamic prompt-token shape and potential cache-reuse tokens without exposing prompts. When the dashboard is started with `--policy`, the same enterprise policy file is used for preview checks.
- Run launch is available through both `/launch` and `POST /api/runs`; it enforces launch policy, runs capability preflight by default, dispatches provider requests, resolves configured provider secret references when needed, and writes run artifacts. When the dashboard is started with `--policy`, launch requests use that policy instead of permissive defaults.
- Launch audit events include capability preflight, launch request, and launched-run completion metadata. Audit payloads do not include prompts, response text, request headers, raw provider payloads, or secret values.
- Completed run lifecycle events can be reviewed through `/api/runs/<run-id>/events`. The endpoint reads only `events.jsonl`, redacts defensively before output, and does not serve raw trace files or provider payloads.
- Static review artifacts can be indexed through `/api/review-artifacts`. The endpoint scans `reports`, `evidence`, `publication-bundles`, `release-bundles`, `campaign-preflight`, and `test-reports`; returns metadata such as schema, status, category, and size; redacts the project root; treats top-level `ok: false` or `passed: false` as failure; keeps telemetry comparability gaps and harness reviews in review state; excludes raw paths and `results.jsonl`; opens only `manifest.json` inside release qualification zip bundles, `publication-bundle-manifest.json` inside run publication bundles, and `matrix-publication-bundle-manifest.json` inside matrix publication bundles. Direct matrix-gate JSON artifacts must declare `agentblaster.matrix-gate.v1` or they are shown as `invalid-schema`. Versioned matrix gates and release qualification manifests with matrix-gate `review_summary` metadata expose only compact `matrix_gate_review_summaries` with `schema_version`, aggregate failure-class counts, missing failure-class result-artifact counts, tool-loop stop-reason counts, missing tool-loop result-artifact counts, invalid tool-call counts, tool-parser repair validity counts, missing parser-repair result-artifact counts, and sanitized metric, actual, and threshold fields for class-specific and parser-repair gate findings. Direct matrix-pressure JSON artifacts and release qualification manifests with matrix-pressure `review_summary` metadata expose compact `matrix_pressure_summaries` with run/case counts, scheduled and concurrent-window prompt-token pressure, concurrency-weighted pressure, shared static prefix groups/tokens, `shared_static_reuse_tokens`, compact engines/models/suites/concurrency levels, and highest-pressure run summaries without copying prompts or largest-case payloads. Direct matrix-saturation JSON artifacts and release qualification manifests with matrix-saturation `review_summary` metadata expose compact `matrix_saturation_summaries` with concurrency levels, result artifact coverage, max queue/rate-limit wait, top queue-pressure entries, and guidance without copying raw result rows. Direct matrix-scorecard JSON artifacts and release qualification manifests with matrix-scorecard `review_summary` metadata expose compact `matrix_scorecard_summaries` with pass rate, result-artifact coverage, compact engine-target IDs, architecture/quantization rollups, judge verdict counts, parser-repair counts, telemetry-quality summary, scorecard concurrency evidence, failure-class counts, and tool-loop stop counts without copying leaderboard entries or raw result rows. Direct selftest JSON artifacts and release qualification manifests with selftest `review_summary` metadata expose compact `selftest_report_summaries` with run id, tier, pass/fail, exit code, duration, browser metadata, and JUnit presence without copying command strings, environment maps, or raw test output. Direct publication-brief and SDLC-validation JSON artifacts, plus release qualification manifests with those `review_summary` categories, expose compact `publication_brief_summaries` and `sdlc_validation_manifest_summaries` with readiness/count, compact engine-target IDs, Chrome GUI coverage, expected evidence, and security booleans only. Direct implementation-status JSON artifacts and release qualification manifests with implementation `review_summary` metadata expose compact `implementation_status_summaries` with implementation state, area counts, harness-engineering case counts, stats-comparability profile counts, keyring/backend posture, and selftest schema posture without copying project roots or file-evidence paths. Direct campaign-preflight manifests and release qualification manifests with campaign-preflight `review_summary` metadata expose only compact `campaign_preflight_summaries` from `manifest.review_summary`; local output paths, matrix paths, policy paths, and dry-run commands are not copied. Direct benchmark-readiness JSON artifacts, campaign-preflight benchmark-readiness indexes, and release qualification manifests with readiness `review_summary` metadata expose compact `benchmark_readiness_summaries` with provider, suite, model, ready state, policy/suite compatibility, contract planning counts, metric coverage score, blocking/warning counts, and redacted provider-auth posture by backend kind only. Direct provider-audit JSON artifacts and release qualification manifests with provider-audit `review_summary` metadata expose compact `provider_audit_summaries` with provider counts, remote counts, error/warning counts, secret-backend posture, policy-control booleans, and finding codes without copying finding messages, secret reference names, dotenv paths, environment values, or keyring contents. Direct provider-contract JSON artifacts and release qualification manifests with provider-contract `review_summary` metadata expose compact `provider_contract_summaries` with mode, check counts, directly checked capabilities, proxy coverage such as `judge_rubric`, and not-covered capabilities such as Anthropic `prompt_caching`. Direct run publication bundles and release qualification manifests with publication `review_summary` metadata expose compact `publication_bundle_summaries` with run ID, artifact count, media-kit roles, missing recommended assets, publication readiness status/counts, and security booleans for raw secrets, raw provider payloads, and `results.jsonl`; readiness `blocked` or unsafe security flags are shown as failing review evidence, while `review-required` stays visible as review evidence. Direct matrix publication bundles and release qualification manifests with `publication/matrix` `review_summary` metadata expose compact `matrix_publication_bundle_summaries` with matrix artifact names, compact engine-target IDs, architecture/quantization rollups, media-kit roles, missing recommended assets, and security booleans for raw secrets, provider payloads, `results.jsonl`, and per-run raw traces. Direct harness-review JSON artifacts and release qualification manifests with harness `review_summary` metadata expose only compact `harness_review_summaries` with suite, generator profile, review status, calibration requirement, surface-count, and assertion-count metadata. Direct engine-advisory JSON artifacts and release qualification manifests with engine advisory `review_summary` metadata expose only compact `engine_advisory_summaries` with engine, priority counts, highest priority, no-dispatch status, priority areas including agentic protocol repair, and aligned artifacts. Direct cleanup JSON artifacts expose only compact `cleanup_report_summaries` with schema, report type, execution mode, action count, selector count, action types, and safety booleans without copying local path lists. Direct evidence-index JSON artifacts and release qualification manifests with evidence-index `review_summary` metadata expose only compact `evidence_index_summaries` with name, artifact count, status counts, readiness state/count metadata, and cleanup evidence rollups without cleanup path lists. Direct suite-audit JSON artifacts and release qualification manifests with suite-audit `review_summary` metadata expose only compact `suite_audit_summaries` with suite, case count, provenance/risk counts, finding codes, finding count, and duplicate-fingerprint count. Direct metric-coverage JSON artifacts and release qualification manifests with metric coverage `review_summary` metadata expose only compact `metric_coverage_summaries` with provider, contract, coverage score, status counts, and comparability group counts/names. Direct normalized-telemetry JSON artifacts and release qualification manifests with normalized-telemetry `review_summary` metadata expose only compact `normalized_telemetry_summaries` with contract, adapter, stats profile, quality counts, comparison guidance, and stats-labeling posture; raw usage maps, raw stats maps, and source maps are not copied into dashboard summaries or detail views. Free-form finding messages, advisory reason text, raw result rows, prompt text, per-field metric notes, raw evidence payloads, full matrix-pressure case payloads, full scorecard leaderboard entries, selftest command strings, selftest environment maps, publication-brief proof text, SDLC fixture commands, and raw test output are not copied into the index.
- The main dashboard page includes a Review evidence panel backed by the same redaction-safe index. Release qualification bundles show compact matrix-gate failure-class and parser-repair summaries, matrix-pressure weighted pressure and shared cache-reuse summaries, matrix-saturation concurrency summaries, matrix-scorecard telemetry/concurrency summaries, implementation-status readiness summaries, publication-bundle readiness summaries, matrix-publication media-kit/engine-target summaries and publication-brief engine-target/architecture/quantization summaries, harness-review calibration summaries, suite-calibration pass/finding summaries, engine-advisory priority summaries, evidence-index readiness and cleanup-evidence summaries, suite-audit dataset-hygiene summaries, and metric-coverage comparability summaries there when the bundle manifest provides them. Run publication bundles show compact media-kit, readiness, and security summaries from `publication-bundle-manifest.json`; matrix publication bundles show compact engine-target, media-kit, and security summaries from `matrix-publication-bundle-manifest.json`.
- `agentblaster quality dashboard-fixture` generates fixture run directories plus a campaign-preflight manifest, campaign-preflight benchmark-readiness index, and redaction-safe release qualification bundle fixture with matrix-gate parser-repair evidence, implementation-status, campaign-preflight, selftest, harness-review, engine-advisory, evidence-index, suite-audit, and metric-coverage summaries so GUI/Chrome tests can exercise the Review evidence panel without real benchmark outputs.
- Small JSON review artifacts can be inspected through `/api/review-artifacts/<path>`. Detail output is defensively redacted, local filesystem paths are replaced, campaign-preflight manifest details return compact review summaries only, and the endpoint still blocks raw paths, `results.jsonl`, zip bundles, oversized JSON, unsupported suffixes, and path traversal.
- Publication brief and SDLC validation manifest JSON artifacts are indexed as compact review evidence. Their detail views also return compact summaries only rather than full proof text, disclosure text, command output, raw test logs, or local paths. Publication brief summaries expose readiness, claim-check counts, proof-point/disclosure/scorecard counts, compact engine-target IDs, architecture/quantization rollups, and security booleans; SDLC validation manifest summaries expose tier/gate counts, Chrome GUI validation coverage, expected release evidence counts, and no-secret/no-raw-payload posture.
- Provider setup stores endpoint metadata and optional `env:` secret references only.
- Provider auth setup can store env references, optional keyring/Keychain secrets, or explicit plaintext dotenv fallback secrets without echoing submitted values. The visible auth panel mirrors the API posture: env mode never accepts raw API-key material, keyring mode writes through the optional OS credential backend, and dotenv mode requires explicit plaintext fallback acknowledgment.
- Provider auth clear removes only the stored reference unless `delete_secret=true` is requested for a writable keyring/dotenv reference; environment-variable secret deletion is refused.
- Secrets are resolved through provider references; launch forms never require raw API keys.
- The security posture panel is derived from redacted provider metadata and run manifests. It flags configured providers that disable TLS verification and does not read raw provider payloads or raw trace files.

Dashboard policy fields:

```yaml
allowed_dashboard_hosts:
  - 127.0.0.1
  - localhost
allowed_dashboard_ports:
  - 8765
allow_dashboard_non_loopback: false
require_dashboard_auth: true
```
