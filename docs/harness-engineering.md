# AgentBlaster Harness Engineering

AgentBlaster treats benchmark harness design as a first-class product surface. Generated suites are deterministic, inspectable YAML artifacts that can be reviewed before any provider is called.

## Profiles

- `prefill`: creates repeated-prefix variants that stress system-prompt prefill, cache reuse, TTFT, and cached-token accounting.
- `concurrency`: clones semantically identical cases into burst workloads that stress queueing, pacing, rate limits, and request isolation.
- `contract-fuzz`: creates streaming, structured-output, and tool-call edge fixtures for OpenAI-compatible and Anthropic-compatible providers.
- `metamorphic`: creates semantically equivalent prompt wrappers that preserve source assertions and expose regressions from harmless wording, formatting, or wrapper-noise changes.
- `cache-replay`: creates warmup, identical replay, suffix mutation, and prefix-invalidation variants for prompt-cache and prefill-cache research.

## Commands

```bash
agentblaster harness profiles
agentblaster harness generate --profile contract-fuzz --suite smoke --repeats 1 --seed 0 --output examples/suites/harness-contract-fuzz.yaml
agentblaster harness generate --profile prefill --suite-file examples/suites/smoke.yaml --repeats 4 --seed 42 --output runs/generated/prefill.yaml
agentblaster harness generate --profile metamorphic --suite-file examples/suites/smoke.yaml --repeats 3 --seed 13 --output runs/generated/metamorphic.yaml
agentblaster harness generate --profile cache-replay --suite cache-control --repeats 2 --seed 17 --output examples/suites/harness-cache-replay.yaml
agentblaster validate-case examples/suites/harness-contract-fuzz.yaml
```

The generator only writes suite files. It does not run a provider, read secrets, or create network traffic.

## Design Rules

- Deterministic output: `profile`, source suite, `repeats`, and `seed` fully define the generated case IDs and marker strings.
- Reviewable artifacts: generated suites use the same `SuiteDefinition` schema as hand-written suites.
- Clear provenance: generated cases are tagged with `harness` plus the profile family.
- No hidden provider assumptions: generated suites should remain runnable across local engines and internet-facing OpenAI/Anthropic-compatible APIs.
- Harness failures are not model failures: malformed generated suites, bad assertions, or broken adapters must be classified as AgentBlaster harness defects.

## Typical Use

Use `contract-fuzz` during adapter work, `prefill` during cache and prompt-template work, `concurrency` during scheduler, batching, and rate-limit work, and `metamorphic` when checking whether agent behavior remains stable under equivalent prompt formulations.

Generated suites should graduate from exploratory fixtures to release gates only after they have at least one known-good provider result, one known-bad calibration case, and documented failure taxonomy coverage.

## Calibration Gates

Generated suites should stay exploratory until calibration evidence is documented. Create a calibration template and gate it before using generated workloads as release criteria:

```bash
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --template-output reports/agentic-local-profiles-calibration.json
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --calibration reports/agentic-local-profiles-calibration.json --output-json reports/agentic-local-profiles-calibration-report.json
```

The calibration gate requires at least one known-good provider result, one known-bad calibration case, documented failure taxonomy coverage, human review, and explicit release-gate approval.
