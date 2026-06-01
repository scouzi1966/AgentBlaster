# Reproducibility Artifacts

AgentBlaster writes reproducibility artifacts with every benchmark run so a result can be audited without trusting terminal output or dashboard screenshots.

## Run Files

Each run directory contains:

- `manifest.json`: run metadata, provider, contract, model, raw-trace mode, retention policy, environment snapshot, model metadata, suite hash, per-case hashes, and the suite snapshot path.
- `suite.json`: canonical JSON snapshot of the effective Pydantic suite definition used by the runner, including defaults.
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

Hashes are computed from canonical JSON with sorted keys and compact separators. YAML formatting, key order, and comments do not affect the hash after parsing. Benchmark-affecting fields do affect the hash, including prompts, messages, tools, response formats, simulated tools, MCP profiles, skills, expected assertions, timeouts, tags, and metadata.

Each result also stores compact `raw_usage` and `raw_stats` snippets so reviewers can see which provider-native fields fed normalized metrics without opening full raw response payloads.

Each result row also stores case metadata such as title, scenario, tags, provenance, risk level, source URL, and license. This keeps exports self-describing even when the original suite file is not present.

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
- Confirm `manifest.json` identifies the provider, contract, model, environment, and exact suite hash.
- Confirm `suite.json` matches the workload being discussed.
- Confirm reports reference the same run ID and suite hash.
- Confirm raw traces are absent or redacted according to the declared raw-trace mode.

## Security Notes

Reproducibility artifacts must not contain raw API keys. Provider credentials are referenced through environment variables or optional OS keyrings, and auth headers are redacted from captured provider payloads unless a user explicitly enables full raw traces for local controlled debugging.

Publication artifacts should cite the run ID, suite SHA-256, model metadata, provider contract, and raw-trace mode so external readers can distinguish benchmark workload changes from engine/model behavior changes.

Use `agentblaster publication-bundle` for externally shareable report bundles. Use `agentblaster bundle` only for replay/debug bundles because replay bundles can include raw traces when they were captured and tracked by `integrity.json`.
