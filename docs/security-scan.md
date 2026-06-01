# Security Scan

`agentblaster security scan` is a deterministic local redaction gate for shareable artifacts. It scans text files, directories, and text entries inside zip files for common secret-like patterns without printing the matched value.

## Usage

```bash
agentblaster security scan   release-bundles/afm-release.agentblaster-release-qualification.zip   --output-json reports/redaction-scan.json
```

The command exits non-zero when findings are detected unless `--no-fail-on-findings` is supplied.

## Scope

The scanner reports pattern names, paths, zip entries, and line numbers. It suppresses matched secret values. Built-in patterns include OpenAI-style API keys, Anthropic-style API keys, GitHub tokens, bearer tokens, and AWS access key IDs.

This is a release gate for common mistakes, not a complete DLP system. Keep raw traces, replay bundles, and provider configs out of publication and release qualification bundles by construction.
