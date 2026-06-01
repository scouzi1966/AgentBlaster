# Harness Engineering Suites

AgentBlaster can generate deterministic benchmark suites that stress emerging agentic harness techniques without calling providers during generation.

## Profiles

- `prefill`: expands source cases with large deterministic system prefixes to expose prefill, cache reuse, and repeated prompt costs.
- `concurrency`: clones source cases into burst workloads to expose queueing, rate limiting, scheduling, and isolation behavior.
- `contract-fuzz`: creates streaming, structured-output, and tool-call protocol edge cases for OpenAI-compatible and Anthropic-compatible endpoints.
- `metamorphic`: creates equivalent wording and wrapper variants that preserve source assertions while testing whether agent behavior is stable under harmless prompt changes.
- `cache-replay`: creates warmup, identical replay, suffix mutation, and static-prefix invalidation variants for prompt-cache diagnostics.

## Provenance

Generated suites include suite-level provenance:

- `origin`: `harness_generated`
- `source_suite`: source suite name
- `generator`: `agentblaster.harness`
- `generator_profile`: selected profile
- `generator_seed`: deterministic generation seed
- `generator_repeats`: repeat count
- `risk_labels`: includes `synthetic` and `harness-generated`

The provenance is written into generated YAML, the run `suite.json` snapshot, the run manifest, and report metadata. Public reports should cite the suite SHA-256 and provenance summary so readers can distinguish engine behavior from workload-generation choices.

## Commands

```bash
agentblaster harness profiles
agentblaster harness generate --profile contract-fuzz --suite smoke --repeats 1 --seed 0 --output examples/suites/harness-contract-fuzz.yaml
agentblaster harness generate --profile metamorphic --suite smoke --repeats 3 --seed 13 --output examples/suites/harness-metamorphic.yaml
agentblaster harness generate --profile cache-replay --suite cache-control --repeats 2 --seed 17 --output examples/suites/harness-cache-replay.yaml
agentblaster validate-case examples/suites/harness-contract-fuzz.yaml
agentblaster run --suite-file examples/suites/harness-contract-fuzz.yaml --engine afm --model mlx-community/Qwen3.6-27B --dry-run
```

## Agent Profile Suites

Representative local-agent workflow suites are generated separately with `agentblaster agents suite --profile all --output examples/suites/agentic-local-profiles.yaml`. See `docs/agent-profiles.md` for OpenCode, OpenClaw, Hermes, and Pi profile details.
