# Agent Fan-Out Suite

AgentBlaster includes a built-in `agent-fanout` suite for synthetic planner/worker/synthesizer request bursts.

The suite is intentionally contract-light: it uses deterministic chat completions rather than tool calls so it can run across local OpenAI-compatible engines, LM Studio, Ollama-compatible endpoints, AFM, and remote OpenAI/Anthropic-compatible providers after normal policy approval.

## Commands

```bash
agentblaster suite-requirements --suite agent-fanout
agentblaster run --suite agent-fanout --engine afm --model mlx-community/Qwen3.6-27B --concurrency 4 --no-raw-traces
agentblaster run --suite agent-fanout --engine lm-studio --model <local-model> --concurrency 4 --no-raw-traces
agentblaster models stress-matrix --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suites agentic-tool-loop,agent-fanout,prefill,harness-engineering,trace-replay --concurrency-levels 1,2,4,8 --output examples/matrices/qwen-gemma-agentic-stress.yaml
```

## Built-In Shape

The built-in suite has four deterministic cases:

- `fanout-planner-outline`
- `fanout-code-worker`
- `fanout-doc-worker`
- `fanout-synthesizer`

Each case shares a short synthetic subagent system prompt, emits a distinct sentinel, and records `queue_ms`, `rate_limit_wait_ms`, `latency_ms`, and `ttft_ms` when available.

## Usage Guidance

Run with `--concurrency 4` to approximate a planner launching worker requests in parallel. Run with `--concurrency 1` as a baseline to separate model/provider latency from queueing and scheduler behavior.

Use generated `concurrency` harness suites when you need wider bursts or repeated variants. Use `agent-fanout` when you need a stable built-in suite for dashboards, readiness dossiers, release gates, and Qwen/Gemma campaign matrices.
