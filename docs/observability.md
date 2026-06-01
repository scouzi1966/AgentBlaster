# Observability And Prometheus Metrics

AgentBlaster can snapshot a provider's Prometheus-style metrics endpoint before and after a benchmark run.

## Provider Configuration

Configure a metrics endpoint when adding a provider:

```bash
agentblaster providers add-preset --preset afm --metrics-url http://127.0.0.1:9999/metrics
agentblaster providers add --name local-engine --contract openai --base-url http://127.0.0.1:9999/v1 --metrics-url http://127.0.0.1:9999/metrics
```

`metrics_url` must not contain embedded credentials or credential-like query parameters. API keys are never sent to the metrics endpoint.

Metrics policy rules:

- Loopback metrics hosts such as `127.0.0.1`, `localhost`, and `::1` are allowed by default.
- Non-loopback metrics hosts are blocked unless the policy file explicitly lists them in `allowed_metrics_url_hosts`.
- `allowed_base_url_hosts` does not implicitly allow a metrics endpoint; observability URLs are controlled separately.

Example policy:

```yaml
allowed_providers:
  - afm
allowed_base_url_hosts:
  - 127.0.0.1
allowed_metrics_url_hosts:
  - 127.0.0.1
allow_remote_providers: false
```

## Run Artifacts

When `metrics_url` is configured, each run records:

- `metrics/prometheus-before.prom`: raw text scrape before dispatch.
- `metrics/prometheus-after.prom`: raw text scrape after dispatch.
- `metrics/prometheus-summary.json`: scrape metadata and numeric deltas for matching sample names.

These artifacts are separate from per-request `results.jsonl` so provider telemetry does not get mixed into normalized benchmark case records. They are included in `integrity.json` and listed in `manifest.json` under `metrics_artifacts`.

## Intended Use

Use Prometheus snapshots to review saturation, queue depth, active requests, cache counters, memory pressure, and provider-specific runtime signals around a run. Treat these metrics as supporting evidence; benchmark scoring should still use normalized per-case records unless a report explicitly opts into engine-native telemetry analysis. Per-case normalized telemetry may include safe HTTP status, request IDs, content type, retry-after, and remaining rate-limit counters from allowlisted response headers, plus `stats_profile` and `stats_comparability` metadata that labels native, measured, inferred, conditional, and missing engine stats before cross-engine claims. It never copies authorization headers, cookies, raw provider headers, or API-key values.
