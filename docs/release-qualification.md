# Release Qualification Bundles

Release qualification bundles collect redaction-safe evidence for CI promotion, AFM release checks, media-supporting benchmark claims, or corporate review.

## Create A Bundle

```bash
agentblaster release qualification-bundle   --name afm-release   --evidence-bundle evidence/toolsim.agentblaster-evidence.zip   --comparison-gate reports/comparison-gate.json   --matrix-gate reports/qwen-gemma-matrix-gate.json   --release-provenance reports/release-provenance.json   --publication-bundle publication-bundles/run.agentblaster-publication.zip   --selftest-report test-reports/selftest/selftest-report.json   --output-dir release-bundles   --audit-log audit/control-plane.jsonl
```

## Allowed Artifact Categories

- Evidence bundles ending in `.agentblaster-evidence.zip`.
- Publication bundles ending in `.agentblaster-publication.zip`.
- Comparison gate JSON artifacts.
- Matrix gate JSON artifacts.
- Release provenance JSON artifacts.
- Selftest report artifacts.

The generated `manifest.json` records every artifact path, category, SHA-256 checksum, and byte size.

## Safety Rules

Release qualification bundles reject obvious raw run artifacts such as `results.jsonl`, paths containing a `raw` segment, and unrecognized zip files. They are intended for review artifacts, not replay/debug bundles.

## Final Redaction Gate

Run `agentblaster security scan release-bundles/<name>.agentblaster-release-qualification.zip --output-json reports/redaction-scan.json` before publishing or attaching a bundle externally. The scanner reports pattern names and locations without printing matched secret values.


## Experiment Context

For corporate or media-facing benchmark campaigns, create and gate an experiment manifest before execution:

```bash
agentblaster experiment manifest --name qwen-gemma-local --objective "Compare local agentic engines." --providers afm,lm-studio --targets qwen3.6-27b-dense,gemma-4-31b-dense --suites trace-replay,prefill --policy agentblaster.policy.yaml --output reports/qwen-gemma-experiment.json
agentblaster experiment gate reports/qwen-gemma-experiment.json --require-policy --output-json reports/qwen-gemma-experiment-gate.json
```

Attach the manifest and gate report alongside evidence bundles and release qualification artifacts so reviewers can see the benchmark scope and acceptance gates that existed before execution.
