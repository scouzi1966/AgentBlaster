# Cancellation Suite

AgentBlaster includes a built-in `cancellation` suite for request lifecycle and stream-abort behavior.

## Commands

```bash
agentblaster suite-requirements --suite cancellation
agentblaster run --suite cancellation --engine afm --model mlx-community/Qwen3.6-27B --no-raw-traces
agentblaster run --suite cancellation --engine openai --model <openai-model> --no-raw-traces --allow-remote
agentblaster harness generate --profile cancellation --suite smoke --repeats 3 --seed 23 --output examples/suites/harness-cancellation.yaml
```

## Built-In Case

The built-in case `cancellation-stream-abort` requests a streaming response, declares `cancel_after_ms: 100`, and expects AgentBlaster to close the stream after events are flowing. The case records:

- `cancel_after_ms`: suite-declared cancellation intent.
- `canceled`: whether AgentBlaster observed the intentional stream abort.
- `cancellation_latency_ms`: elapsed time until the harness closed the stream.
- `ttft_ms` and `latency_ms`: timing context around stream startup and request lifecycle.

## Scoring

A cancellation case passes when cancellation is observed. If the provider completes normally or does not expose a stream that can be closed, AgentBlaster records a failure with `engine_feature_gap` rather than `model_quality`.

## Usage Guidance

Use the built-in suite as a stable smoke test for cancellation support. Use the `cancellation` harness profile when you need repeated abort timings or broader generated workloads. Treat cancellation support as contract and request-lifecycle behavior, not model quality.
