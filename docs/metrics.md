# Metric Coverage And Normalization

AgentBlaster normalizes provider-specific runtime stats into common `results.jsonl` fields. Engines still vary in what they expose, so metric coverage must be explicit in reports and release evidence.

## Coverage Reports

Inspect a configured provider without contacting the endpoint:

```bash
agentblaster providers metric-coverage --provider afm --output-json reports/afm-metric-coverage.json
```

Inspect the static catalog for supported contract families:

```bash
agentblaster providers metric-coverage --catalog --output-json reports/metric-coverage-catalog.json
```

Normalize a captured or synthetic provider response sample without contacting an endpoint:

```bash
agentblaster catalog normalize-telemetry \
  samples/ollama-response.json \
  --contract native \
  --native-adapter ollama \
  --output-json reports/ollama-normalized-telemetry.json
```

Use sample normalization when onboarding engines or reviewing provider changes. It records which fields were populated, which source key produced each value, and which normalized fields remain missing. For OpenAI-compatible MLX wrappers, optional `stats`, `metrics`, or `timings` blocks can use explicit millisecond, second, or nanosecond aliases for TTFT, load, prefill, and decode timings; throughput can be native or derived when token counts and explicit-duration fields are present.

The telemetry mapping catalog includes a static `stats_comparability` block. It documents field semantics for AgentBlaster-measured latency/TTFT, native prefill/decode durations, inferred throughput, cache-read/cache-write accounting, and profile-specific guidance for AFM MLX, MLX-LM, Rapid MLX, oMLX, Ollama native, LM Studio native, OpenAI-compatible, and Anthropic-compatible targets. This catalog is a no-dispatch artifact; it contains no provider payloads, API keys, secret references, or raw traces.

The command reports each normalized field as:

- `native`: exposed directly by the provider contract or native adapter.
- `measured`: measured by AgentBlaster around dispatch, scheduling, parsing, or validation.
- `inferred`: derived from native fields, for example tokens/sec from token counts and durations.
- `conditional`: available only when an endpoint/version returns optional fields.
- `unavailable`: not exposed by the contract or not mapped by the current adapter.

Coverage reports also include a `comparability` section that groups fields into timing/throughput, token/cache accounting, agent protocol behavior, and telemetry provenance. Each group is classified as:

- `publication-grade`: every field in the group is native or measured.
- `advisory-only`: all fields exist, but at least one is inferred or conditional and must be labeled before comparison.
- `partial`: one or more fields are unavailable, so reports must disclose missing metrics.
- `unavailable`: the group has no mapped fields for that provider contract or native adapter.

## Normalized Field Groups

Timing and throughput:

- `latency_ms`
- `queue_ms`
- `rate_limit_wait_ms`
- `ttft_ms`
- `prompt_eval_ms`
- `decode_ms`
- `tokens_per_second_prefill`
- `tokens_per_second_decode`

Token and cache accounting:

- `input_tokens`
- `output_tokens`
- `total_tokens`
- `cached_input_tokens`
- `cache_write_tokens`
- `cache_hit_ratio`

Agent correctness and protocol behavior:

- `tool_calls_requested`
- `tool_calls_emitted`
- `tool_calls_valid`
- `invalid_tool_call_count`
- `tool_parser_repair_valid`
- `tool_loop_enabled`
- `tool_loop_rounds`
- `tool_loop_tool_call_count`
- `tool_loop_max_tool_calls`
- `tool_loop_stop_reason`
- `structured_output_valid`
- `judge_verdict_valid`
- `finish_reason`
- `cancel_after_ms`
- `canceled`
- `cancellation_latency_ms`

Provenance:

- `status_code`
- `provider_request_id`
- `response_content_type`
- `provider_rate_limit_remaining`
- `provider_retry_after_ms`
- `raw_usage`
- `raw_stats`

Sample normalization writes `agentblaster.normalized-telemetry.v1` artifacts. These artifacts contain the normalized values, source map, field-quality labels, comparison-readiness metadata, and missing-field list. They should not contain raw prompts, API keys, or complete provider payloads; use minimized usage/stat samples for review. Release qualification bundles and claim-readiness gates accept these artifacts with `--normalized-telemetry` and preserve only compact contract, adapter, stats-profile, quality-count, comparison-guidance, and stats-labeling posture in release-facing summaries.

Run result rows also carry telemetry provenance:

- `telemetry_schema_version`: current normalized telemetry schema.
- `telemetry_sources`: map from each populated normalized field to the raw provider or AgentBlaster measurement source.
- `telemetry_quality`: map from each populated normalized field to `native`, `measured`, `inferred`, `conditional`, `raw_provenance`, or `unknown`.
- `telemetry_comparison_readiness`: compact per-row readiness metadata for publication-grade versus advisory normalized fields.
- `telemetry_missing`: normalized fields that were not available from this response.

The flat fields such as `input_tokens`, `prompt_eval_ms`, `tokens_per_second_decode`, `tool_loop_stop_reason`, and `judge_verdict_valid` remain convenient for reports and CSV exports. The provenance fields are the audit trail that explains whether each value came from OpenAI usage, Anthropic usage, Ollama native nanosecond stats, LM Studio stats, AgentBlaster timers, deterministic harness validators, safe HTTP metadata, or derived calculations. Request IDs and rate-limit counters are captured only from allowlisted response headers already redacted by the adapter layer; authorization headers, cookies, and raw provider payload headers are not copied.

Telemetry audit artifacts include run-level `comparison_readiness` so reports can disclose whether required metrics are native/measured, inferred/conditional, unknown, incomplete, or unavailable before using them in cross-engine claims.

Completed runs can be audited for telemetry completeness:

```bash
agentblaster telemetry-audit runs/<run-id> --output-json reports/<run-id>-telemetry-audit.json
```

Use `--required-field` for metrics that will appear in a comparison or publication claim. Use `--fail-on-findings` in CI or release gates after deciding which fields are mandatory for the claim.

## Reporting Rule

Do not compare inferred or conditional metrics as if they are native measurements. Publication reports should cite metric coverage and the `comparability.groups[].claim_guidance` values when comparing engines with different contracts, especially OpenAI-compatible servers versus Anthropic-compatible local profiles, Ollama native, or LM Studio native endpoints.
