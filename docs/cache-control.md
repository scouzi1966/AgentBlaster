# Cache-Control And Prefill Diagnostics

AgentBlaster supports case-level `cache_control` metadata for cache-aware benchmark planning. The first serialization target is Anthropic Messages-style cache control on static system prefixes.

## Built-In Suite

```bash
agentblaster suite-requirements --suite cache-control
agentblaster suite-footprint --suite cache-control --output-json reports/cache-control-footprint.json
agentblaster run --suite cache-control --engine anthropic --model <anthropic-model> --no-raw-traces
```

The built-in `cache-control` suite stresses repeated static system prefixes and tool-catalog prefixes. It declares metrics such as `cached_input_tokens`, `cache_write_tokens`, `cache_hit_ratio`, `ttft_ms`, and `tokens_per_second_prefill`.

## Provider Behavior

Anthropic-compatible adapters serialize `cache_control` onto the static system block. OpenAI-compatible providers keep the metadata in suite definitions, prompt-footprint reports, and run manifests, but do not receive provider-specific cache-control fields.

Use provider metric coverage reports to distinguish native cache accounting from unavailable or inferred fields:

```bash
agentblaster providers metric-coverage --provider anthropic --output-json reports/anthropic-metric-coverage.json
```
