# AgentBlaster Reporting

AgentBlaster reports are generated from completed run directories. Report generation reads normalized artifacts and does not call providers or require API keys.

Run directories also include `events.jsonl`, a redacted lifecycle stream suitable for dashboard timelines and operational audits. Reports continue to use normalized result and summary artifacts as their source of truth; lifecycle events are intentionally prompt-free and response-free.

## Formats

```bash
agentblaster report runs/<run-id> --format html,md,json,publication,card,png,pdf
```

- `html`: human-readable engineering report.
- `md`: markdown report for pull requests, issues, and docs.
- `json`: compact `summary.json` for automation.
- `publication`: structured `publication.json` for corporate/media pipelines.
- `card`: self-contained `report-card.svg` for social posts, slide decks, and internal status updates.
- `png`: `report-card.png` rendered from the same SVG card for image-first media workflows. This requires the optional `agentblaster[reports]` dependency group.
- `pdf`: dependency-free `report.pdf` executive summary for corporate review packets.

## Result Exports

```bash
agentblaster export runs/<run-id> --format jsonl,csv,parquet
```

- `jsonl`: copies normalized `results.jsonl` for replayable row-level analysis.
- `csv`: writes `exports/results.csv` with scalar columns plus JSON-encoded compact list/dict fields such as tags and metric provenance.
- `parquet`: writes `exports/results.parquet` with the same normalized export columns for warehouse-style analysis. This path requires the optional `agentblaster[exports]` dependency group, which installs `pyarrow`; the base package stays lightweight and cross-platform without it.

## Publication Manifest

`publication.json` contains:

- Run identity: suite, provider, model, engine target when known, contract, timestamp, concurrency.
- Provider metadata: safe endpoint, endpoint host, remote/local status, TLS verification state, custom CA bundle path, adapter name/version, native adapter, and declared capabilities.
- Model metadata: revision, architecture, quantization, tokenizer, chat template, context length.
- Retention policy: artifact classification, intended run retention, intended raw-trace retention, and notes.
- Scorecard: pass rate, latency, TTFT, queue wait, cache hit ratio, decode rate, cost, tool-call counts, judge-rubric verdict validity, and failure-class counts.
- Scenario summary: per-scenario case counts, pass/fail counts, latency, TTFT, and decode throughput.
- Highlights: short label/value pairs suitable for presentation templates.
- Publication readiness: a machine-readable `agentblaster.publication-readiness.v1` block with ready/review/blocked status, blocker and warning counts, companion artifact presence, and next-step guidance for external media or corporate review.
- Case failures: normalized failed case IDs, classes, and messages.
- Security notes: raw trace mode and confirmation that raw provider payloads are excluded.

## Metric Provenance

`results.jsonl` stores normalized metrics plus compact raw metric provenance:

- `raw_usage`: provider `usage` object when present, redacted and stored separately from full raw responses.
- `raw_stats`: native stats or stream metadata used to derive normalized timing and throughput fields.
- `telemetry_quality`: per-field native/measured/inferred/conditional provenance labels used to avoid overclaiming cross-engine comparability.
- `telemetry_comparison_readiness`: compact per-row readiness metadata used by telemetry audits and review artifacts.
- `cancel_after_ms`, `canceled`, and `cancellation_latency_ms`: cancellation workload intent and observed stream-abort outcome when a case is designed to test cancellation behavior.

These fields are intended for auditability when providers use different metric names. They are not a replacement for raw trace artifacts, and they must not contain auth headers or full provider payloads. Use `agentblaster providers metric-coverage --provider afm --output-json reports/afm-metric-coverage.json` to document which normalized metrics are native, measured, inferred, conditional, or unavailable for a provider before publishing comparisons. The report's `comparability` groups classify timing/throughput, token/cache, agent protocol, and provenance metric families as publication-grade, advisory-only, partial, or unavailable. The report's `claim_contract` block reduces those groups into leaderboard eligibility, disclosure-required groups, and primary score policy so media/corporate reports do not silently rank engines on incomparable provider-native stats.

Audit a completed run before making cross-engine metric claims:

```bash
agentblaster telemetry-audit \
  runs/<run-id> \
  --required-field latency_ms \
  --required-field tokens_per_second_decode \
  --output-json reports/<run-id>-telemetry-audit.json
```

The audit reads only normalized `results.jsonl` rows. It reports field completeness, metric source counts, source quality buckets, missing normalized fields, and blocker findings when required metrics do not meet the requested completeness threshold.

## Structured Output Validation

Structured-output benchmark cases can use `response_format` with `type: json_schema`. AgentBlaster validates the returned JSON against the embedded schema for common JSON Schema constraints such as object properties, required fields, arrays, primitive types, enums, constants, and `additionalProperties: false`.

Schema failures mark the case as failed even when the provider returned HTTP 200 and syntactically valid JSON.

## Cancellation Validation

Cancellation cases declare `cancel_after_ms`. For streaming-compatible adapters, AgentBlaster closes the stream after the configured elapsed time once stream events are being processed, records `canceled=true`, and scores the case as successful when cancellation is observed. If a cancellation case completes normally without an observed abort, the case fails with `engine_feature_gap`.

Cancellation results are normalized fields, not raw traces. Reports and exports can compare cancellation support without exposing provider payloads.

## Tool-Call Validation

Tool-call benchmark cases validate both the tool name and the emitted argument object. AgentBlaster compares tool arguments against the offered function `parameters` schema using the same deterministic schema validator used for structured output.

`tool_calls_valid` counts only calls that are well-formed, were offered by the suite, and satisfy their argument schema. Required-tool cases fail when the expected tool is emitted with malformed or schema-invalid arguments.

Bounded deterministic tool loops are exposed through normalized result fields: `tool_loop_enabled`, `tool_loop_rounds`, `tool_loop_tool_call_count`, `tool_loop_max_tool_calls`, and `tool_loop_stop_reason`. These fields are safe to report when raw traces are off because they do not include prompt text, tool arguments, tool-result payloads, or provider responses.

Matrix gates can aggregate those fields into `tool_loop_stop_summary` and `tool_loop_artifacts_missing`, and can enforce stop-reason limits with repeated `--max-tool-loop-stop-reason reason=count` options. Release qualification, claim readiness, evidence indexes, engine improvement advisories, and dashboard review artifacts preserve only compact counts plus sanitized threshold-finding metadata such as `tool_loop_stop_reason.max_tool_calls_reached`; they do not copy raw result rows or finding messages.

Judge-rubric workloads are exposed through `judge_verdict_valid`. Matrix gates can aggregate those fields into `judge_rubric_cases`, `judge_verdicts_valid`, `judge_verdict_valid_rate_percent`, and `judge_verdict_artifacts_missing`, and can enforce minimum validity with `--min-judge-verdict-valid-rate`. This gives generated evaluator-style suites a release-gateable signal without storing prompts, candidate answers, or raw judge traces in release artifacts.

Tool-parser repair workloads are exposed through `invalid_tool_call_count` and `tool_parser_repair_valid`. Matrix gates can aggregate those fields into `invalid_tool_call_count`, `tool_parser_repair_cases`, `tool_parser_repairs_valid`, `tool_parser_repair_valid_rate_percent`, and `tool_parser_repair_artifacts_missing`, and can enforce hard protocol thresholds with `--max-invalid-tool-calls` and `--min-tool-parser-repair-valid-rate`. This lets local-agent comparisons fail fast on malformed tool calls or parser-repair regressions while still excluding raw tool arguments and provider responses from release artifacts.

## SVG Report Card

`report-card.svg` is dependency-free and designed as a 1200x630 card. It can be opened directly in browsers or inserted into slide decks. `--format png` writes `report-card.png` from the same SVG source when the optional `agentblaster[reports]` dependencies are installed. When `publication.json` is generated in the same command as `card`, `png`, and `pdf`, AgentBlaster writes the publication manifest after companion assets so the readiness block can report which artifacts are present.

The SVG intentionally uses normalized metrics only. It excludes raw traces, raw provider responses, and secrets.

## PDF Executive Summary

`report.pdf` is dependency-free and derived from the same normalized manifest/result fields as the HTML and SVG reports. It is intentionally compact: run identity, scorecard metrics, model/environment metadata, failure-class summary, and security notes. It excludes raw traces, raw provider responses, API keys, and request headers.

## Publication Briefs

After claim readiness and matrix scorecards exist, generate a publication brief for media, executive, or corporate review:

```bash
agentblaster release publication-brief \
  --name qwen-gemma-local \
  --claim-readiness reports/qwen-gemma-claim-readiness.json \
  --matrix-scorecard reports/qwen-gemma-local-summary-matrix-scorecard.json \
  --output-json reports/qwen-gemma-publication-brief.json \
  --output-md reports/qwen-gemma-publication-brief.md
```

The JSON uses `agentblaster.publication-brief.v1`. It summarizes readiness, proof points, scorecards, compact engine-target IDs, architecture/quantization rollups, protocol-repair posture, media-kit readiness, disclosures, recommended wording, and the security boundary. Engine-target, architecture/quantization, and media-kit readiness are derived from compact claim-readiness evidence such as matrix scorecard summaries, publication bundle summaries, and matrix publication bundle summaries; the command does not open publication ZIP bundles. It reads compact review artifacts only and does not open `results.jsonl`, raw traces, provider configs, keyrings, dotenv files, or remote endpoints.

## Protocol Repair Posture

Generate a standalone protocol-repair posture when reviewers need a focused signoff artifact for invalid tool-call emissions and parser-repair validity:

```bash
agentblaster release protocol-repair \
  --name qwen-gemma-local \
  --claim-readiness reports/qwen-gemma-claim-readiness.json \
  --matrix-scorecard reports/qwen-gemma-local-summary-matrix-scorecard.json \
  --matrix-gate reports/qwen-gemma-matrix-gate.json \
  --output-json reports/qwen-gemma-protocol-repair.json \
  --output-md reports/qwen-gemma-protocol-repair.md
```

The JSON uses `agentblaster.protocol-repair-posture.v1`. It summarizes scorecard parser-repair cases, matrix-gate parser-repair cases, invalid tool-call counts, matrix-gate evidence gaps, disclosures, recommendations, and a security boundary. Direct matrix scorecards and matrix gates take precedence over compact copies embedded in claim-readiness artifacts so the posture report does not double-count the same matrix. The command reads compact review artifacts only and does not open `results.jsonl`, raw traces, provider configs, keyrings, dotenv files, or remote endpoints.

## Workflow Readiness

Before dispatching a large local or remote agentic campaign, generate a workflow-readiness report to prove the planned inputs cover the intended workflow surfaces:

```bash
agentblaster release workflow-readiness \
  --name qwen-gemma-agentic-campaign \
  --matrix matrices/qwen-gemma-agentic.yaml \
  --matrix-pressure-audit reports/qwen-gemma-pressure-audit.json \
  --harness-review reports/emerging-workflows-harness-review.json \
  --output-json reports/qwen-gemma-workflow-readiness.json \
  --output-md reports/qwen-gemma-workflow-readiness.md
```

The JSON uses `agentblaster.workflow-readiness.v1`. By default it requires coverage for tool calling, tool loops, structured output, concurrency, prefill/cache pressure, MCP, LCP, skills, cancellation, and harness engineering. Use repeated `--required-surface` options to narrow or customize the gate for a specific campaign. The report reads suite definitions, matrix definitions, matrix-pressure audits, and harness-review artifacts only. It does not dispatch providers, resolve API keys, inspect keyrings, open `results.jsonl`, copy prompts/tool arguments, read raw traces, or contact local or remote endpoints.

## Security Posture

Create an enterprise security posture report before sharing benchmark outputs with corporate reviewers or external media:

```bash
agentblaster security posture \
  --name qwen-gemma-security \
  --policy agentblaster.policy.yaml \
  --provider-audit reports/provider-audit.json \
  --redaction-scan reports/publication-redaction-scan.json \
  --review-artifact reports/qwen-gemma-workflow-readiness.json \
  --review-artifact reports/qwen-gemma-protocol-repair.json \
  --output-json reports/security-posture.json \
  --output-md reports/security-posture.md
```

The JSON uses `agentblaster.security-posture.v1`. It summarizes policy blockers/warnings, optional keyring/Apple Keychain dependency posture, provider audit counts, plaintext dotenv fallback usage, TLS warnings, redaction scan findings, and review-artifact security flags. The command is static: it does not dispatch providers, resolve API keys, read keyring values, inspect environment variable values, contact endpoints, or copy matched secret values from redaction scans. Keyring/Apple Keychain remains optional; environment variable references are the portable enterprise baseline, while dotenv plaintext fallback is treated as local-development-only evidence that requires review.

Attach protocol-repair, workflow-readiness, and security-posture artifacts to release qualification and claim-readiness evidence so dashboard review pages, evidence indexes, and release bundle manifests can summarize them consistently:

```bash
agentblaster release qualification-bundle \
  --output-dir release-bundles \
  --protocol-repair-posture reports/qwen-gemma-protocol-repair.json \
  --workflow-readiness reports/qwen-gemma-workflow-readiness.json \
  --security-posture reports/security-posture.json

agentblaster release claim-readiness \
  --protocol-repair-posture reports/qwen-gemma-protocol-repair.json \
  --workflow-readiness reports/qwen-gemma-workflow-readiness.json \
  --security-posture reports/security-posture.json
```

## Publication Bundles

Create a shareable bundle after generating report artifacts:

```bash
agentblaster report runs/<run-id> --format html,md,json,publication,card,png,pdf
agentblaster publication-bundle runs/<run-id> --output-dir publication-bundles
```

Publication bundles are distinct from replay bundles:

- `publication-bundle` includes only allowlisted shareable artifacts such as `manifest.json`, `suite.json`, `summary.json`, `report.html`, `report.md`, `report.pdf`, `publication.json`, `report-card.svg`, `report-card.png`, `integrity.json`, and optional `signature.json`.
- It adds a generated `publication-bundle-manifest.json` with schema `agentblaster.publication-bundle.v1`, the packaged artifact list, a `media_kit` block using `agentblaster.media-kit.v1`, the embedded publication readiness block, and explicit security flags confirming that raw provider payloads, API keys, request headers, exports, caches, and `results.jsonl` are excluded.
- The `media_kit` block maps each packaged JSON/PDF/HTML/Markdown/SVG/PNG asset to its professional role, intended audiences, media type, usage guidance, card dimensions when applicable, recommended corporate-review/media-post packets, and missing recommended assets.
- It excludes `results.jsonl`, `raw/`, raw Prometheus scrapes, exports, caches, and any unrecognized files.
- It verifies `integrity.json` before packaging and fails if tracked artifacts changed or are missing.
- It requires `publication.json` so the bundle always carries the structured corporate/media payload.
- `bundle` remains the replay/debug artifact and can include any integrity-tracked run files, including raw traces when they were captured.
- Matrix campaigns can be packaged separately with `agentblaster matrix publication-bundle reports/qwen-gemma-matrix-summary.json --output-dir publication-bundles` after generating matrix reports and scorecards. Matrix publication bundles include only the matrix summary, matrix reports, matrix scorecards, a generated `matrix-publication-bundle-manifest.json` with schema `agentblaster.matrix-publication-bundle.v1`, and scorecard SVG/PNG media cards; they exclude per-run `results.jsonl`, raw traces, provider payloads, exports, API keys, and request headers.
- The matrix publication-bundle manifest includes compact `engine_targets`, architecture rollups, and quantization rollups from the scorecard plus the same `agentblaster.media-kit.v1` structure, so downstream dashboard, deck, media, and corporate-report generators can locate target-family IDs, structured scorecard JSON, executive PDFs, and 1200x630 SVG/PNG scorecard cards without inspecting raw benchmark rows or opening the scorecard JSON.

## Run Comparison

`agentblaster compare` reports whole-run aggregates and scenario-level aggregates. Scenario rows make it easier to spot regressions isolated to prefill/cache, structured output, tool calling, trace replay, built-in agent fan-out, or generated concurrency workloads.

JSON comparison output includes `scenario_summary` for each run.

## Matrix Reports

Executed matrices can be reported from the JSON artifact produced by `--matrix-summary-json`:

```bash
agentblaster matrix report reports/qwen-gemma-matrix-summary.json --format html,md,json,pdf
```

Matrix reports include:

- Matrix identity, source path, timestamp, attempted run count, completed run count, failed run count, and case pass rate.
- Provider-level aggregates for provider x model comparisons.
- Model-level aggregates for Qwen/Gemma or future architecture comparisons.
- A dependency-free PDF executive summary for review packets.
- One row per attempted matrix entry. Successful entries include run id, compact engine-target metadata when known, and paths to per-run summary, manifest, and result artifacts, stored relative to the matrix summary JSON directory. Failed entries from `--continue-on-error` include error type/message and no raw artifacts.
- A shareable `agentblaster-matrix-report-v1` JSON payload with compact engine-target IDs and no raw provider payloads, raw traces, or API keys.

Before execution, use a pressure audit to document what the matrix is expected to stress:

```bash
agentblaster matrix pressure-audit \
  examples/matrices/qwen-gemma-stress.yaml \
  --output-json reports/qwen-gemma-stress-pressure.json
```

This artifact is static and no-dispatch. It helps reviewers distinguish a high-prefill matrix from a high-concurrency or high-output-token matrix before interpreting runtime results, and it reports potential cache-reuse tokens for repeated static-prefix workloads.

## Matrix Scorecards

Use matrix scorecards when the audience needs a concise leaderboard rather than a full audit report:

```bash
agentblaster matrix scorecard reports/qwen-gemma-matrix-summary.json --format html,md,json,card,png,pdf
agentblaster matrix publication-bundle reports/qwen-gemma-matrix-summary.json --output-dir publication-bundles
```

Scorecards rank matrix entries by pass rate, latency, decode throughput, engine, model, suite, architecture, and quantization. When `results_path` artifacts are available, the scorecard also includes normalized latency, TTFT, queue wait, rate-limit wait, cache hit ratio, prefill/decode throughput, cost, tool-call counts, invalid tool-call counts, tool-parser repair validity counts, tool-loop stop-reason counts, judge-rubric verdict validity, fan-out scenario counts, cancellation counts/latency, failure-class counts, telemetry completeness, telemetry quality counts, and telemetry comparison guidance. The top-level scorecard block includes `telemetry_quality_summary` so publication reviewers can distinguish native, measured, inferred, conditional, raw-provenance, unknown, and unavailable metrics before making cross-engine claims. It also includes aggregate `invalid_tool_call_count`, `tool_parser_repair_cases`, `tool_parser_repairs_valid`, and `tool_parser_repair_valid_rate_percent` fields so protocol-repair behavior is comparable across local and remote OpenAI/Anthropic-compatible engines without opening raw traces. It also includes compact `concurrency_evidence` with observed concurrency levels, artifact coverage, max queue/rate-limit wait, top pressure entries, and guidance for whether the scorecard supports a saturation/concurrency claim. When run manifests are available, the scorecard also emits architecture and quantization rollups so Qwen3.6 dense, Gemma 4 dense, and future model-family comparisons can be reviewed without mixing incompatible quantization classes. Missing result artifacts remain explicit so partial matrix summaries are still publishable without hiding gaps.

The `card` format writes a dependency-free `matrix-scorecard.svg` sized for media posts, decks, and corporate status updates, including compact parser-repair, telemetry-quality, and concurrency-evidence labels. The `png` format writes a PNG rendering of the same card when `agentblaster[reports]` is installed. The `pdf` format writes a compact executive summary for corporate review packets and includes the same parser-repair, telemetry, and concurrency evidence summaries as Markdown and HTML. The scorecard JSON payload uses `agentblaster-matrix-scorecard-v1` and includes compact engine-target IDs, `architecture_summary`, `quantization_summary`, `failure_class_summary`, `tool_loop_stop_summary`, `telemetry_quality_summary`, `concurrency_evidence`, invalid tool-call counts, tool-parser repair validity counts, judge-rubric verdict-validity counts, `leaderboard`, and `entries`. It excludes raw provider payloads, raw traces, API keys, and request headers.

## Matrix Saturation Reports

Use saturation reports after executing a matrix with repeated engine/model/suite entries at multiple concurrency levels:

```bash
agentblaster matrix saturation-report \
  reports/qwen-gemma-matrix-summary.json \
  --output-json reports/qwen-gemma-matrix-saturation.json
```

The report groups entries by engine, provider, model, and suite, then compares each higher concurrency level against the lowest-concurrency baseline. Findings call out pass-rate drops, average and p95 latency regressions, queue wait, rate-limit wait, and decode-throughput drops. The top-level `concurrency_evidence` block summarizes multi-level group coverage, maximum observed queue/rate-limit wait, top queue-pressure entries, and publication guidance without copying raw rows. The top-level `ok` field is false when error findings are present, such as failed matrix runs or pass-rate drops beyond the configured threshold. This is the executed-result companion to `matrix pressure-audit`: pressure audit states what the matrix intended to stress before dispatch, while saturation report shows how the engine behaved after dispatch.

The JSON payload uses `agentblaster.matrix-saturation.v1` and reads only matrix summaries plus normalized result rows. It excludes raw provider payloads, raw traces, API keys, and request headers.

## Comparison Gates

Use comparison gates for CI or release regression checks after two runs have been produced:

```bash
agentblaster compare-gate   runs/<baseline>   runs/<candidate>   --min-pass-rate 95   --max-pass-rate-drop 2   --max-avg-latency-regression-pct 15   --max-p95-latency-regression-pct 20   --max-avg-ttft-regression-pct 20   --min-decode-tokens-per-second-ratio 0.90   --output-json reports/comparison-gate.json
```

The command exits non-zero when a threshold is violated and writes a machine-readable report when `--output-json` is supplied. It only reads normalized run summaries/results and does not read raw traces or raw provider payloads.

For corporate or media claims, pair comparison gates with `agentblaster telemetry-audit` outputs for each compared run. A latency or throughput regression is easier to defend when the metric exists for every case and the source map shows whether values are provider-native, AgentBlaster-measured, or inferred.


## Matrix Gates

Use matrix gates for CI or release checks after an executed matrix summary is written:

```bash
agentblaster matrix gate   reports/qwen-gemma-matrix-summary.json   --require-all-runs-complete   --max-failed-runs 0   --min-completed-runs 4   --min-case-pass-rate 95   --max-failed-cases 0   --max-failure-class engine_protocol_bug=0   --max-tool-loop-stop-reason max_tool_calls_reached=0   --min-judge-verdict-valid-rate 95   --output-json reports/qwen-gemma-matrix-gate.json
```

The command exits non-zero when a threshold is violated, prints `schema_version: agentblaster.matrix-gate.v1` in text output, and writes `agentblaster.matrix-gate.v1` JSON when `--output-json` is supplied. Use that schema-versioned artifact for claim readiness and release qualification. Standard run/case thresholds read only the normalized matrix summary JSON. Failure-class thresholds such as `--max-failure-class engine_protocol_bug=0`, tool-loop thresholds such as `--max-tool-loop-stop-reason max_tool_calls_reached=0`, and judge-rubric thresholds such as `--min-judge-verdict-valid-rate 95` also read the normalized `results.jsonl` artifacts referenced by the matrix summary and fail if those artifacts are missing or unreadable. Matrix gates never read raw traces, raw provider payloads, provider configs, API keys, or request headers.

Use `--include-failure-class-summary` or `--include-tool-loop-summary` when reviewers need observed failure-class or tool-loop stop-reason counts in the matrix-gate artifact without turning those counts into blocking thresholds. Summary-only loading records missing referenced result artifacts, but only threshold options make missing result artifacts fail the gate.

For `agentic-tool-loop` campaigns, `final_response` is the expected successful loop stop reason and is safe to include as review evidence. `max_tool_calls_reached` should normally be thresholded to zero for release gates because it means the bounded harness stopped a loop before the model produced a final answer.
