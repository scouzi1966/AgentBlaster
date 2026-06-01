# Failure Taxonomy

AgentBlaster classifies failed cases so benchmark reports can separate model behavior from engine, protocol, environment, and harness failures.

- `model_quality`: the provider returned a valid response, but the model did not satisfy the benchmark assertion.
- `engine_protocol_bug`: the provider response violated the selected API contract, including malformed tool-call envelopes or invalid tool-call arguments.
- `engine_feature_gap`: the provider lacks or failed a required lifecycle feature such as streaming cancellation.
- `engine_runtime_bug`: the provider timed out or returned runtime/server errors.
- `environmental`: credentials, connectivity, provider availability, or deployment setup prevented a valid test.
- `rate_limit`: the provider rejected work due to rate or quota limits.
- `harness_bug`: AgentBlaster or the deterministic fixture setup is invalid.

Tool-call handling is intentionally split: a missing expected tool call is `model_quality`, while an invalid API-native tool envelope is `engine_protocol_bug`. This keeps local parser/contract issues visible when comparing OpenClaw-style, OpenCode-style, Hermes-style, and MCP/LCP-heavy agentic suites.

Run publication manifests, markdown/HTML/PDF reports, and matrix scorecards expose `failure_class_summary` and `tool_loop_stop_summary` counts so reviewers can distinguish model-quality failures, engine/contract issues, and bounded agentic-loop stop behavior without inspecting raw traces.

Matrix gates can enforce class-specific thresholds with repeated `--max-failure-class class=count` options, for example `--max-failure-class engine_protocol_bug=0` for release campaigns where OpenAI/Anthropic contract violations must block publication even if aggregate pass rate remains high.

Engine improvement advisories consume `agentblaster.matrix-gate.v1` `failure_class_summary`, `failure_class_artifacts_missing`, `tool_loop_stop_summary`, `tool_loop_artifacts_missing`, `invalid_tool_call_count`, `tool_parser_repair_cases`, `tool_parser_repairs_valid`, and sanitized gate findings to create failure-taxonomy remediation, agentic-loop-control, agentic-protocol-repair, and evidence-integrity priorities. Stale or unversioned matrix gates become `evidence-integrity` priorities instead of being trusted. This keeps AFM roadmap work tied to the owner of the failure class, bounded tool-loop stop reason, or parser-repair protocol defect rather than treating every failed benchmark as a generic reliability issue.

Claim-readiness reports also preserve matrix-gate failure-class summaries, missing failure-class result-artifact counts, tool-loop stop-reason summaries, missing tool-loop result-artifact counts, and class-specific findings, even when the gate passes. This gives corporate or media reviewers a compact explanation of residual allowed failures and bounded tool-loop behavior without requiring access to raw traces or provider payloads.

Release qualification bundle manifests copy the same matrix-gate aggregate failure-class and tool-loop stop metadata into per-artifact `review_summary` fields. These compact summaries keep the matrix-gate `schema_version` plus class, metric, actual, and threshold fields for class-specific gate findings but omit free-form finding messages. This keeps archived release evidence understandable while still excluding normalized result rows, raw traces, prompts, responses, provider configs, API keys, and request headers.
