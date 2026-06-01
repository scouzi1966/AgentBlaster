# AgentBlaster Harness Engineering

AgentBlaster treats benchmark harness design as a first-class product surface. Generated suites are deterministic, inspectable YAML artifacts that can be reviewed before any provider is called.

## Profiles

- `prefill`: creates repeated-prefix variants that stress system-prompt prefill, cache reuse, TTFT, and cached-token accounting.
- `concurrency`: clones semantically identical cases into burst workloads that stress queueing, pacing, rate limits, and request isolation.
- `cancellation`: creates streaming abort workloads that stress request cancellation, stream shutdown, and cancellation latency.
- `contract-fuzz`: creates streaming, structured-output, and tool-call edge fixtures for OpenAI-compatible and Anthropic-compatible providers.
- `metamorphic`: creates semantically equivalent prompt wrappers that preserve source assertions and expose regressions from harmless wording, formatting, or wrapper-noise changes.
- `cache-replay`: creates warmup, identical replay, suffix mutation, and prefix-invalidation variants for prompt-cache and prefill-cache research.
- `emerging-workflows`: combines MCP fixture catalogs, LCP context bundles, skill prefixes, simulated tools, tool-loop routing, cache controls, and prefill metrics in one local-agent workflow stack.
- `judge-rubric`: creates deterministic structured-output evaluator cases that test model-judge rubric following without a second judge model or external service.

## Commands

```bash
agentblaster harness profiles
agentblaster harness generate --profile contract-fuzz --suite smoke --repeats 1 --seed 0 --output examples/suites/harness-contract-fuzz.yaml
agentblaster harness generate --profile prefill --suite-file examples/suites/smoke.yaml --repeats 4 --seed 42 --output runs/generated/prefill.yaml
agentblaster harness generate --profile metamorphic --suite-file examples/suites/smoke.yaml --repeats 3 --seed 13 --output runs/generated/metamorphic.yaml
agentblaster harness generate --profile cache-replay --suite cache-control --repeats 2 --seed 17 --output examples/suites/harness-cache-replay.yaml
agentblaster harness generate --profile cancellation --suite smoke --repeats 3 --seed 23 --output examples/suites/harness-cancellation.yaml
agentblaster harness generate --profile emerging-workflows --suite smoke --repeats 2 --seed 37 --output examples/suites/harness-emerging-workflows.yaml
agentblaster harness generate --profile judge-rubric --suite smoke --repeats 2 --seed 31 --output examples/suites/harness-judge-rubric.yaml
agentblaster harness review --suite-file examples/suites/harness-contract-fuzz.yaml --output-json reports/harness-contract-fuzz-review.json
agentblaster validate-case examples/suites/harness-contract-fuzz.yaml
```

The generator only writes suite files. It does not run a provider, read secrets, or create network traffic.

## Design Rules

- Deterministic output: `profile`, source suite, `repeats`, and `seed` fully define the generated case IDs and marker strings.
- Reviewable artifacts: generated suites use the same `SuiteDefinition` schema as hand-written suites.
- Clear provenance: generated cases are tagged with `harness` plus the profile family.
- Mixed emerging-workflow cases intentionally combine MCP fixture catalogs, LCP context bundles, skill prefixes, simulated tools, tool-loop routing, cache controls, and prefill metrics so local-agent prompt stacks can be tested as a system rather than isolated features.
- No hidden provider assumptions: generated suites should remain runnable across local engines and internet-facing OpenAI/Anthropic-compatible APIs.
- Harness failures are not model failures: malformed generated suites, bad assertions, or broken adapters must be classified as AgentBlaster harness defects.

## Typical Use

Use `contract-fuzz` during adapter work, `prefill` during cache and prompt-template work, `concurrency` during scheduler, batching, and rate-limit work, `cancellation` during stream abort and request-lifecycle work, `metamorphic` when checking whether agent behavior remains stable under equivalent prompt formulations, `emerging-workflows` when testing combined MCP/LCP/skills/tool-loop/cache local-agent stacks, and `judge-rubric` when evaluating whether a model can follow strict rubric and verdict schemas.

Generated suites should graduate from exploratory fixtures to release gates only after they have at least one known-good provider result, one known-bad calibration case, and documented failure taxonomy coverage.

The static harness review artifact should be created before dispatch. It records the generated profile, seed, repeats, case count, capability surfaces, assertion families, metrics, tags, risk signals, and calibration requirement without embedding prompts, raw traces, provider payloads, API keys, or keyring values.
Generated campaign plans include per-suite harness-review commands and calibration template/report command slots. Harness reviews are threaded into evidence indexes, engine advisories, release qualification, and claim readiness; completed calibration reports are accepted as release qualification and claim-readiness evidence, and failed calibration reports block release-gate qualification when supplied.

Use `agentblaster suite-footprint` and `agentblaster matrix pressure-audit` before execution to review scheduled prompt tokens, shared static-prefix groups, and potential cache-reuse tokens without contacting providers.

## Calibration Gates

Generated suites should stay exploratory until calibration evidence is documented. Create a calibration template and gate it before using generated workloads as release criteria:

```bash
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --template-output reports/agentic-local-profiles-calibration.json
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --calibration reports/agentic-local-profiles-calibration.json --output-json reports/agentic-local-profiles-calibration-report.json
```

The calibration gate requires at least one known-good provider result, one known-bad calibration case, documented failure taxonomy coverage, human review, and explicit release-gate approval.
