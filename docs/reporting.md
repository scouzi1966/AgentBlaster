# AgentBlaster Reporting

AgentBlaster reports are generated from completed run directories. Report generation reads normalized artifacts and does not call providers or require API keys.

## Formats

```bash
agentblaster report runs/<run-id> --format html,md,json,publication,card
```

- `html`: human-readable engineering report.
- `md`: markdown report for pull requests, issues, and docs.
- `json`: compact `summary.json` for automation.
- `publication`: structured `publication.json` for corporate/media pipelines.
- `card`: self-contained `report-card.svg` for social posts, slide decks, and internal status updates.

## Publication Manifest

`publication.json` contains:

- Run identity: suite, provider, model, contract, timestamp, concurrency.
- Provider metadata: safe endpoint, endpoint host, remote/local status, TLS verification state, custom CA bundle path, adapter name/version, native adapter, and declared capabilities.
- Model metadata: revision, architecture, quantization, tokenizer, chat template, context length.
- Retention policy: artifact classification, intended run retention, intended raw-trace retention, and notes.
- Scorecard: pass rate, latency, TTFT, queue wait, cache hit ratio, decode rate, cost, and tool-call counts.
- Scenario summary: per-scenario case counts, pass/fail counts, latency, TTFT, and decode throughput.
- Highlights: short label/value pairs suitable for presentation templates.
- Case failures: normalized failed case IDs, classes, and messages.
- Security notes: raw trace mode and confirmation that raw provider payloads are excluded.

## Metric Provenance

`results.jsonl` stores normalized metrics plus compact raw metric provenance:

- `raw_usage`: provider `usage` object when present, redacted and stored separately from full raw responses.
- `raw_stats`: native stats or stream metadata used to derive normalized timing and throughput fields.

These fields are intended for auditability when providers use different metric names. They are not a replacement for raw trace artifacts, and they must not contain auth headers or full provider payloads. Use `agentblaster providers metric-coverage --provider afm --output-json reports/afm-metric-coverage.json` to document which normalized metrics are native, measured, inferred, conditional, or unavailable for a provider before publishing comparisons.

## Structured Output Validation

Structured-output benchmark cases can use `response_format` with `type: json_schema`. AgentBlaster validates the returned JSON against the embedded schema for common JSON Schema constraints such as object properties, required fields, arrays, primitive types, enums, constants, and `additionalProperties: false`.

Schema failures mark the case as failed even when the provider returned HTTP 200 and syntactically valid JSON.

## Tool-Call Validation

Tool-call benchmark cases validate both the tool name and the emitted argument object. AgentBlaster compares tool arguments against the offered function `parameters` schema using the same deterministic schema validator used for structured output.

`tool_calls_valid` counts only calls that are well-formed, were offered by the suite, and satisfy their argument schema. Required-tool cases fail when the expected tool is emitted with malformed or schema-invalid arguments.

## SVG Report Card

`report-card.svg` is dependency-free and designed as a 1200x630 card. It can be opened directly in browsers, inserted into slide decks, or converted to PNG by downstream tooling.

The SVG intentionally uses normalized metrics only. It excludes raw traces, raw provider responses, and secrets.

## Publication Bundles

Create a shareable bundle after generating report artifacts:

```bash
agentblaster report runs/<run-id> --format html,md,json,publication,card
agentblaster publication-bundle runs/<run-id> --output-dir publication-bundles
```

Publication bundles are distinct from replay bundles:

- `publication-bundle` includes only allowlisted shareable artifacts such as `manifest.json`, `suite.json`, `summary.json`, `report.html`, `report.md`, `publication.json`, `report-card.svg`, `integrity.json`, and optional `signature.json`.
- It excludes `results.jsonl`, `raw/`, raw Prometheus scrapes, exports, caches, and any unrecognized files.
- It verifies `integrity.json` before packaging and fails if tracked artifacts changed or are missing.
- It requires `publication.json` so the bundle always carries the structured corporate/media payload.
- `bundle` remains the replay/debug artifact and can include any integrity-tracked run files, including raw traces when they were captured.

## Run Comparison

`agentblaster compare` reports whole-run aggregates and scenario-level aggregates. Scenario rows make it easier to spot regressions isolated to prefill/cache, structured output, tool calling, trace replay, or generated concurrency workloads.

JSON comparison output includes `scenario_summary` for each run.

## Matrix Reports

Executed matrices can be reported from the JSON artifact produced by `--matrix-summary-json`:

```bash
agentblaster matrix report reports/qwen-gemma-matrix-summary.json --format html,md,json
```

Matrix reports include:

- Matrix identity, source path, timestamp, attempted run count, completed run count, failed run count, and case pass rate.
- Provider-level aggregates for provider x model comparisons.
- Model-level aggregates for Qwen/Gemma or future architecture comparisons.
- One row per attempted matrix entry. Successful entries include run id and paths to per-run summary, manifest, and result artifacts. Failed entries from `--continue-on-error` include error type/message and no raw artifacts.
- A shareable `agentblaster-matrix-report-v1` JSON payload that excludes raw provider payloads, raw traces, and API keys.

## Matrix Scorecards

Use matrix scorecards when the audience needs a concise leaderboard rather than a full audit report:

```bash
agentblaster matrix scorecard reports/qwen-gemma-matrix-summary.json --format html,md,json
```

Scorecards rank matrix entries by pass rate, latency, decode throughput, engine, model, and suite. When `results_path` artifacts are available, the scorecard also includes normalized latency, TTFT, cache hit ratio, prefill/decode throughput, cost, tool-call counts, and telemetry completeness. Missing result artifacts remain explicit so partial matrix summaries are still publishable without hiding gaps.

The scorecard JSON payload uses `agentblaster-matrix-scorecard-v1` and excludes raw provider payloads, raw traces, API keys, and request headers.


## Comparison Gates

Use comparison gates for CI or release regression checks after two runs have been produced:

```bash
agentblaster compare-gate   runs/<baseline>   runs/<candidate>   --min-pass-rate 95   --max-pass-rate-drop 2   --max-avg-latency-regression-pct 15   --max-p95-latency-regression-pct 20   --max-avg-ttft-regression-pct 20   --min-decode-tokens-per-second-ratio 0.90   --output-json reports/comparison-gate.json
```

The command exits non-zero when a threshold is violated and writes a machine-readable report when `--output-json` is supplied. It only reads normalized run summaries/results and does not read raw traces or raw provider payloads.


## Matrix Gates

Use matrix gates for CI or release checks after an executed matrix summary is written:

```bash
agentblaster matrix gate   reports/qwen-gemma-matrix-summary.json   --require-all-runs-complete   --max-failed-runs 0   --min-completed-runs 4   --min-case-pass-rate 95   --max-failed-cases 0   --output-json reports/qwen-gemma-matrix-gate.json
```

The command exits non-zero when a threshold is violated. It only reads the normalized matrix summary JSON and does not read raw traces, raw provider payloads, or provider configs.
