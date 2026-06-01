# Telemetry Normalization

AgentBlaster compares engines that expose usage and timing metrics through different contracts. The telemetry normalization layer converts known raw response shapes into a single conservative per-case schema while preserving compact raw usage and raw stats for audit.

## Normalized Fields

Core normalized fields include latency, TTFT, input/output/total tokens, cache read/write tokens, cache hit ratio, native load/prompt/decode timing, prefill and decode throughput, finish reason, raw usage, and raw stats. Missing fields remain `null`; AgentBlaster does not guess unavailable provider metrics.

## Supported Mapping Families

- `generic-openai-chat`: OpenAI-compatible Chat Completions usage and finish reasons.
- `openai-responses`: OpenAI Responses-compatible usage and status fields.
- `anthropic-messages`: Anthropic Messages usage, cache read tokens, and cache creation tokens.
- `afm-mlx-openai-compatible`: AFM MLX OpenAI-compatible usage enriched with optional native MLX stats.
- `ollama-native`: native Ollama counts and nanosecond timings converted to milliseconds and tokens/sec.
- `lm-studio-native`: LM Studio usage and optional stats such as TTFT and decode throughput.
- `mlx-lm-openai-compatible`: MLX-LM OpenAI-compatible wrappers with optional native stats.
- `rapid-mlx-openai-compatible`: Rapid MLX OpenAI-compatible wrappers with optional prefill/decode stats.

## Commands

```bash
agentblaster catalog telemetry-mappings
agentblaster catalog telemetry-mappings --format json --output reports/telemetry-mappings.json
agentblaster catalog telemetry-mappings --format markdown --output reports/telemetry-mappings.md
```

## Security And Audit Policy

Telemetry normalization never reads secrets, environment variables, browser state, local model caches, or external endpoints. It operates only on response dictionaries already captured by adapters. Raw provider payloads should still be governed by run-level raw trace policy; the normalizer only preserves compact `raw_usage` and `raw_stats` fields needed for explainable metric mapping.

## Comparison Guidance

Use normalized metrics for tables and gates only when the metric source is comparable. For example, Ollama native `prompt_eval_duration` is nanoseconds and must be converted before comparing against AFM or LM Studio millisecond stats. Cache metrics should distinguish cache reads from cache writes because Anthropic-compatible contracts expose both while most OpenAI-compatible Chat endpoints expose only cached prompt-token details, if any.

## Runner Integration

`result_from_response` uses the telemetry normalizer before writing `BenchmarkResult` rows. Token counts, cache counters, cache hit ratios, native timing fields, throughput fields, raw usage, raw stats, and finish reasons now come from the same normalization path used by the telemetry mapping catalog. Cost estimation runs after normalization so cache read/write token pricing uses the normalized counters.

The older helper functions in `agentblaster.runner` remain available for compatibility, but new result construction should treat `agentblaster.telemetry.normalize_response_telemetry` as the authoritative raw-to-normalized mapping layer.
