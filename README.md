# AgentBlaster

AgentBlaster is a local agentic benchmark suite for OpenAI-compatible, Anthropic-compatible, and engine-native local inference servers.

The goal is to measure the hard parts of local agent workloads: repeated long system prompts, tool schemas, skills, MCP-style tool catalogs, structured output, streaming, cancellation, concurrency, prompt-cache reuse, and professional reporting.

## Initial Scope

- Engines: AFM MLX, mlx-lm, Ollama MLX, LM Studio, oMLX, Rapid-MLX, and vLLM-MLX.
- Models: Qwen3.6-27B dense and Gemma 4 31B dense.
- Interfaces: OpenAI Chat Completions first, then OpenAI Responses and Anthropic Messages.
- Outputs: CLI results, normalized JSONL, optional dashboard, HTML/PDF/PNG reports.

## Repository Status

This repository is freshly scaffolded from the initial PRD. The product requirements live in [docs/prd.md](docs/prd.md).

## Implemented CLI Foundation

```bash
agentblaster version
agentblaster engines list
agentblaster engines probe --engine afm --base-url http://127.0.0.1:9999/v1
agentblaster providers add --name openai --contract openai --base-url https://api.openai.com/v1 --api-key-env OPENAI_API_KEY --remote
agentblaster providers list
agentblaster providers auth test --provider openai
agentblaster providers probe openai
agentblaster run --suite smoke --engine openai --model gpt-4.1-mini --no-raw-traces
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --offline
agentblaster run --suite smoke --engine afm --model mlx-community/Qwen3.6-27B --policy agentblaster.policy.yaml
```

Provider profiles are stored locally without raw API keys. API keys can be referenced through environment variables today; optional OS keyring support is defined for persistent secret entry.

Run execution already includes the first enterprise controls: raw traces can be disabled, remote providers can be blocked with `--offline`, and YAML policy files can allowlist providers and endpoint hosts.

## Planned Benchmark CLI

```bash
agentblaster report runs/<run-id> --format html
```
