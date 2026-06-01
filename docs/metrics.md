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

The command reports each normalized field as:

- `native`: exposed directly by the provider contract or native adapter.
- `measured`: measured by AgentBlaster around dispatch, scheduling, parsing, or validation.
- `inferred`: derived from native fields, for example tokens/sec from token counts and durations.
- `conditional`: available only when an endpoint/version returns optional fields.
- `unavailable`: not exposed by the contract or not mapped by the current adapter.

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
- `structured_output_valid`
- `finish_reason`

Provenance:

- `raw_usage`
- `raw_stats`

## Reporting Rule

Do not compare inferred or conditional metrics as if they are native measurements. Publication reports should cite metric coverage when comparing engines with different contracts, especially OpenAI-compatible servers versus Ollama native or LM Studio native endpoints.
