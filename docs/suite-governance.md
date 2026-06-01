# Suite Governance

AgentBlaster suites are executable benchmark inputs. Treat them as reviewable artifacts before they are used for local model claims, remote API spending, media posts, or corporate reports.

## Static Suite Audit

Run a static audit without contacting providers or resolving secrets:

```bash
agentblaster suite-audit --suite toolcall
agentblaster suite-audit --suite-file examples/suites/toolsim.yaml --output-json reports/toolsim-suite-audit.json
```

The audit reports:

- Case count, provenance counts, risk counts, and scenario counts.
- Offered tool schema names.
- Deterministic simulated tools.
- MCP fixture profiles.
- Skill packs.
- Structured-output, streaming, cancellation, and trace-replay case counts.
- Dataset hygiene metadata, including duplicate workload fingerprints computed from prompt, message, tool, response-format, simulator, MCP/LCP, skill, and expected-assertion fields without printing prompt text.
- Governance findings such as missing `source_url`, missing `license`, high-risk cases, duplicate workload fingerprints, and unnamed tool schemas.

The audit is intentionally static. It does not dispatch provider requests, execute tools, start MCP servers, read provider configs, resolve API keys, or inspect raw run artifacts.

## Recommended Review Flow

1. Run `agentblaster suite-audit` for each built-in or file-based suite under review.
2. Run `agentblaster catalog simulated-tools`, `agentblaster catalog mcp-profiles`, and `agentblaster catalog skills` for capability-surface inventory.
3. Approve capability names into `agentblaster.policy.yaml` allowlists.
4. Use `agentblaster run --dry-run --plan-json ...` to confirm prompt/cost estimates before dispatch.
5. Create `agentblaster evidence bundle ...` to package the suite audit JSON, catalog JSON, policy file, and release provenance JSON for corporate review.
6. Attach the evidence bundle and final publication bundle to corporate or external benchmark evidence.

## Governance Rules

Externally derived cases should include `source_url` and `license`. High-risk cases should be reviewed for data sensitivity, prompt-injection content, and whether they require stricter raw-trace retention settings. Duplicate workload fingerprints should be deduped or explicitly justified before release gates so a small repeated fixture does not overstate engine reliability. Tool schemas should always be named so policy allowlists can enforce explicit approval.

Tool-capable cases should declare `max_tool_calls` when they model multi-step agent loops. When `max_tool_calls > 1`, AgentBlaster can perform bounded deterministic fixture tool-result round trips before evaluating the final answer. Enterprise policy can enforce this with `require_max_tool_calls_for_tool_cases: true` and cap the bound with `max_tool_calls_per_case`.

Policy can also enforce governance metadata before dispatch:

```yaml
allowed_case_provenance:
  - synthetic_representative
  - internal_regression
  - customer_trace_sanitized
allowed_case_risk_levels:
  - low
  - medium
allow_high_risk_cases: false
require_source_url_for_external_cases: true
require_license_for_external_cases: true
```

Use stricter provenance allowlists for release gates when only synthetic, internal, or sanitized customer-trace fixtures are approved. Permit `primary_source` or `public_benchmark_adapted` only when source and license metadata are present.

## Suite Calibration

Generated or synthetic representative suites need calibration before they are used as release gates. Use `agentblaster suite-calibration` to write a manifest template and evaluate calibration evidence:

```bash
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --template-output reports/agentic-local-profiles-calibration.json
agentblaster suite-calibration --suite-file examples/suites/agentic-local-profiles.yaml --calibration reports/agentic-local-profiles-calibration.json --output-json reports/agentic-local-profiles-calibration-report.json
```

A passing calibration requires known-good evidence, known-bad evidence, failure taxonomy coverage, human review, and release-gate approval. The command is static and does not contact providers. Completed `agentblaster.suite-calibration-report.v1` artifacts can be supplied to release qualification and claim readiness; failed reports block release-gate qualification when supplied.
