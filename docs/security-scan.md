# Security Scan

`agentblaster security scan` is a deterministic local redaction gate for shareable artifacts. It writes `agentblaster.redaction-scan.v1` reports and scans text files, directories, text entries inside zip files, and unsafe or sensitive zip member names for common secret-like patterns without printing the matched value.

## Usage

```bash
agentblaster security scan   release-bundles/afm-release.agentblaster-release-qualification.zip   --output-json reports/redaction-scan.json
agentblaster security scan   publication-bundles/run.agentblaster-publication.zip   --output-json reports/publication-redaction-scan.json
```

The command exits non-zero when findings are detected unless `--no-fail-on-findings` is supplied.

Use the generated JSON artifact directly with `agentblaster release claim-readiness --redaction-scan reports/redaction-scan.json`. Claim readiness requires the `agentblaster.redaction-scan.v1` schema and copies only compact scan counts plus pattern-count summaries, not matched values or raw scan lines.

## Scope

The scanner reports pattern names, redacted file-location suffixes, zip entries, and line numbers. It suppresses matched values and does not echo absolute scan paths. Built-in patterns include Anthropic-style API keys, OpenAI-style API keys, GitHub tokens, bearer tokens, AWS access key IDs, unsafe zip member paths such as absolute or parent-traversal entries, and obvious local filesystem paths such as macOS user/volume/private paths and Windows user paths. Anthropic `sk-ant-...` keys are classified before the generic OpenAI `sk-...` pattern so release reports preserve useful provider-specific finding names without exposing the key value.

This is a release gate for common mistakes, not a complete DLP system. Keep raw traces, replay bundles, and provider configs out of publication and release qualification bundles by construction. The scanner opens text entries inside zip files, so publication bundles should be scanned before they are attached to claim-readiness packets or distributed externally.
