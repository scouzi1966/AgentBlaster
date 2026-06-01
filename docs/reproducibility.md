# Reproducibility Artifacts

AgentBlaster writes reproducibility artifacts with every benchmark run so a result can be audited without trusting terminal output or dashboard screenshots.

## Run Files

Each run directory contains:

- `manifest.json`: run metadata, provider, contract, model, compact engine-target metadata, raw-trace mode, retention policy, environment snapshot, model metadata, suite hash, per-case hashes, and the suite snapshot path.
- `suite.json`: canonical JSON snapshot of the effective Pydantic suite definition used by the runner, including defaults.
- `events.jsonl`: redacted run lifecycle events for progress, dashboard timelines, and operational audits.
- `results.jsonl`: normalized per-case benchmark records.
- `summary.json`: aggregate result summary for full suite runs.
- `raw/`: optional raw provider responses, controlled by raw trace mode and redaction policy.
- `metrics/`: optional Prometheus before/after snapshots and numeric deltas when the provider config includes `metrics_url`.
- `integrity.json`: SHA-256 hashes for every run artifact except `integrity.json` itself.
- `signature.json`: optional HMAC-SHA256 signature over the integrity manifest artifact hashes.

## Suite And Case Hashes

`manifest.json` records:

- `suite_sha256`: hash of the canonical suite payload.
- `case_sha256`: map of each case ID to the hash of that effective case definition.
- `suite_snapshot_path`: path to the stored suite snapshot, currently `suite.json`.
- `suite_provenance`: source, license, generation profile, seed, repeats, and risk labels when available.
- `retention_policy`: classification, intended run retention days, intended raw-trace retention days, and governance notes.
- `metrics_artifacts`: Prometheus snapshot artifacts captured for the run, when configured.
- `provider_metadata`: safe provider endpoint, endpoint host, remote/local status, adapter identity, declared capabilities, metrics host, TLS verification state, and custom CA bundle path when configured.
- `engine_target`: compact target-family metadata when the provider maps to a built-in target, including target ID, display name, primary scoring contract, workflow surfaces, telemetry profiles, prefill/concurrency challenge classes, and native metric policy.

Hashes are computed from canonical JSON with sorted keys and compact separators. YAML formatting, key order, and comments do not affect the hash after parsing. Benchmark-affecting fields do affect the hash, including prompts, messages, tools, response formats, simulated tools, MCP profiles, skills, expected assertions, timeouts, tags, and metadata.

Each result also stores compact `raw_usage` and `raw_stats` snippets so reviewers can see which provider-native fields fed normalized metrics without opening full raw response payloads. Successful rows include `telemetry_schema_version`, `telemetry_sources`, `telemetry_quality`, `telemetry_comparison_readiness`, and `telemetry_missing` so cross-engine comparisons can identify native, inferred, measured, conditional, and unavailable fields. Telemetry audit artifacts aggregate those rows into run-level `comparison_readiness` for publication review. Tool-loop rows include only compact loop metadata such as round count, fixture tool-call count, declared maximum, and stop reason; prompt text and deterministic tool-result payloads remain outside publication bundles.

Each result row also stores case metadata such as title, scenario, tags, provenance, risk level, source URL, and license. This keeps exports self-describing even when the original suite file is not present.

## Run Lifecycle Events

`events.jsonl` uses the `agentblaster-run-event-v1` schema. Current events include:

- `run_started`: run identity, compact engine target ID when known, case count, concurrency, raw-trace mode, and whether provider metric scraping was enabled.
- `case_completed`: case ID, scenario, pass/fail status, HTTP status when available, failure class, queue/rate-limit wait, latency, TTFT, and cancellation observation fields.
- `run_completed`: final case counts, pass/fail counts, run timestamps, duration, and request throughput.

Lifecycle events are intentionally not a raw trace stream. They do not include prompts, system prompts, messages, response text, tool arguments, request headers, raw provider payloads, API keys, or keyring references. Values are redacted defensively before writing, and `events.jsonl` is included in `integrity.json`.

The optional dashboard exposes the same lifecycle stream through `/api/runs/<run-id>/events`. Dashboard output is defensively redacted again and remains limited to operational metadata.

## Integrity Manifest

`integrity.json` lets a reviewer detect modified artifacts after a run. It includes checksums for `manifest.json`, `suite.json`, `results.jsonl`, reports, exports, raw traces when enabled, and other generated files present before integrity writing.

## Signature Manifest

Create a signature after a run has written `integrity.json`:

```bash
export AGENTBLASTER_SIGNING_KEY="<secret from your CI or enterprise secret manager>"
agentblaster sign runs/<run-id> --key-env AGENTBLASTER_SIGNING_KEY --key-id ci-release-key
```

Verify both `signature.json` and the underlying artifact integrity:

```bash
agentblaster verify-signature runs/<run-id> --key-env AGENTBLASTER_SIGNING_KEY
```

Signature behavior:

- `signature.json` signs the canonical `integrity.json` payload with HMAC-SHA256.
- The signing key is read only from an environment variable and is never written to artifacts, reports, or terminal output.
- `key_id` is non-secret metadata for identifying which external key should verify the run.
- Signature verification fails if the signing key is wrong, `integrity.json` changes, or any artifact tracked by `integrity.json` is missing or modified.

Use this model when reviewing a published result:

- Confirm `integrity.json` verifies all included artifacts.
- If present, confirm `signature.json` verifies with the expected external signing key.
- Confirm `manifest.json` identifies the provider, engine target when known, contract, model, environment, and exact suite hash.
- Confirm `suite.json` matches the workload being discussed.
- Confirm reports reference the same run ID and suite hash.
- Confirm raw traces are absent or redacted according to the declared raw-trace mode.

## Security Notes

Reproducibility artifacts must not contain raw API keys. Provider credentials are referenced through environment variables or optional OS keyrings, and auth headers are redacted from captured provider payloads unless a user explicitly enables full raw traces for local controlled debugging.

Publication artifacts should cite the run ID, suite SHA-256, model metadata, engine target when known, provider contract, and raw-trace mode so external readers can distinguish benchmark workload changes from engine/model behavior changes.

Use `agentblaster publication-bundle` for externally shareable report bundles. Use `agentblaster bundle` only for replay/debug bundles because replay bundles can include raw traces when they were captured and tracked by `integrity.json`.

Publication bundles include `integrity.json` and include `signature.json` when the run was signed before bundling. If `signature.json` is present but no longer matches `integrity.json`, bundle creation fails and the run must be signed again. The generated `publication-bundle-manifest.json` includes a compact `integrity` block with signature presence, key ID, signed artifact count, and unsigned publication artifact names so reviewers can see signature coverage without accessing the signing key.
