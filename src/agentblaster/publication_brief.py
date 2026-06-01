from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentblaster.errors import ConfigError


PUBLICATION_BRIEF_SCHEMA_VERSION = "agentblaster.publication-brief.v1"
CLAIM_READINESS_SCHEMA_VERSION = "agentblaster.claim-readiness.v1"
MATRIX_SCORECARD_REPORT_TYPE = "agentblaster-matrix-scorecard-v1"
MEDIA_KIT_SCHEMA_VERSION = "agentblaster.media-kit.v1"


def build_publication_brief(
    *,
    name: str,
    claim_readiness: Path,
    matrix_scorecards: list[Path] | None = None,
    release_provenance: Path | None = None,
    evidence_index: Path | None = None,
) -> dict[str, Any]:
    claim_payload = _load_json_artifact(claim_readiness, expected_schema=CLAIM_READINESS_SCHEMA_VERSION)
    scorecards = [_matrix_scorecard_summary(_load_json_artifact(path), path) for path in matrix_scorecards or []]
    release_summary = _release_provenance_summary(_load_json_artifact(release_provenance), release_provenance) if release_provenance else None
    evidence_summary = _evidence_index_summary(_load_json_artifact(evidence_index), evidence_index) if evidence_index else None
    claim_summary = _claim_readiness_summary(claim_payload, claim_readiness)
    media_kit = _media_kit_summary(claim_payload)
    engine_targets = _brief_engine_targets(claim_payload, scorecards, media_kit)
    architecture_summary = _brief_scorecard_group_summary(
        claim_payload,
        scorecards,
        media_kit,
        "architecture_summary",
        key="model_architecture",
    )
    quantization_summary = _brief_scorecard_group_summary(
        claim_payload,
        scorecards,
        media_kit,
        "quantization_summary",
        key="quantization",
    )
    protocol_repair_summary = _protocol_repair_summary(claim_payload, scorecards)
    disclosures = _disclosures(
        claim_summary,
        claim_payload,
        scorecards,
        release_summary,
        evidence_summary,
        media_kit,
        protocol_repair_summary,
    )
    proof_points = _proof_points(
        claim_summary,
        claim_payload,
        scorecards,
        release_summary,
        evidence_summary,
        media_kit,
        protocol_repair_summary,
    )
    recommended_language = _recommended_language(_safe_name(name), claim_summary, disclosures)
    source_artifacts = [_artifact_ref("claim_readiness", claim_readiness)]
    source_artifacts.extend(_artifact_ref("matrix_scorecard", path) for path in matrix_scorecards or [])
    if release_provenance:
        source_artifacts.append(_artifact_ref("release_provenance", release_provenance))
    if evidence_index:
        source_artifacts.append(_artifact_ref("evidence_index", evidence_index))
    return {
        "schema_version": PUBLICATION_BRIEF_SCHEMA_VERSION,
        "name": _safe_name(name),
        "audience": ["media", "corporate review", "executive review"],
        "ready": claim_summary["ready"],
        "claim_readiness": claim_summary,
        "engine_targets": engine_targets,
        "architecture_summary": architecture_summary,
        "quantization_summary": quantization_summary,
        "protocol_repair_summary": protocol_repair_summary,
        "matrix_scorecards": scorecards,
        "media_kit": media_kit,
        "release_provenance": release_summary,
        "evidence_index": evidence_summary,
        "proof_points": proof_points,
        "disclosures": disclosures,
        "recommended_language": recommended_language,
        "security": {
            "source_artifact_count": len(source_artifacts),
            "source_artifacts": source_artifacts,
            "contains_raw_provider_payloads": False,
            "contains_raw_traces": False,
            "contains_secrets": False,
            "stores_raw_secrets": False,
            "path_policy": "Input paths are reduced to relative artifact names or basenames for absolute/parent-relative paths.",
            "notes": [
                "Publication briefs read compact review artifacts only.",
                "They do not open results.jsonl, raw traces, provider configs, keyrings, dotenv files, or remote endpoints.",
                "A brief is a signoff aid; it does not replace rerunning validation before external publication.",
            ],
        },
    }


def write_publication_brief_json(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_publication_brief_markdown(report: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_publication_brief(report), encoding="utf-8")
    return output


def format_publication_brief(report: dict[str, Any]) -> str:
    readiness = report.get("claim_readiness", {})
    recommended = report.get("recommended_language", {})
    scorecards = report.get("matrix_scorecards", [])
    media_kit = report.get("media_kit") if isinstance(report.get("media_kit"), dict) else {}
    engine_targets = report.get("engine_targets") if isinstance(report.get("engine_targets"), list) else []
    architecture_summary = report.get("architecture_summary") if isinstance(report.get("architecture_summary"), list) else []
    quantization_summary = report.get("quantization_summary") if isinstance(report.get("quantization_summary"), list) else []
    protocol_repair_summary = (
        report.get("protocol_repair_summary") if isinstance(report.get("protocol_repair_summary"), dict) else {}
    )
    lines = [
        "# AgentBlaster Publication Brief",
        "",
        "## Executive Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Claim | `{_markdown_cell(report.get('name'))}` |",
        f"| Ready | `{str(report.get('ready')).lower()}` |",
        f"| Checks | `{readiness.get('passed', 0)}/{readiness.get('checks', 0)} passed` |",
        f"| Blockers | `{readiness.get('blockers', 0)}` |",
        f"| Warnings | `{readiness.get('warnings', 0)}` |",
        f"| Media kit | `{_media_kit_status_text(media_kit)}` |",
        f"| Engine targets | `{_engine_target_ids_text(engine_targets)}` |",
        f"| Architectures | `{_scorecard_group_names_text(architecture_summary, 'model_architecture')}` |",
        f"| Quantization | `{_scorecard_group_names_text(quantization_summary, 'quantization')}` |",
        f"| Protocol repair | `{_protocol_repair_status_text(protocol_repair_summary)}` |",
        f"| Source artifacts | `{report.get('security', {}).get('source_artifact_count', 0)}` |",
        "",
        "## Recommended Language",
        "",
        f"Headline: {_markdown_cell(recommended.get('headline'))}",
        "",
        _markdown_cell(recommended.get("short_summary")),
        "",
        "## Proof Points",
        "",
    ]
    lines.extend(f"- {_markdown_cell(item)}" for item in report.get("proof_points", []) or ["No proof points supplied."])
    lines.extend(["", "## Media Kit Readiness", ""])
    lines.extend(
        [
            "| Field | Value |",
            "| --- | --- |",
            f"| Status | `{_markdown_cell(media_kit.get('status'))}` |",
            f"| Bundles | `{media_kit.get('bundle_count', 0)} total, {media_kit.get('run_bundle_count', 0)} run, {media_kit.get('matrix_bundle_count', 0)} matrix` |",
            f"| Assets | `{media_kit.get('asset_count', 0)}` |",
            f"| Missing recommended assets | `{_join_or_none(media_kit.get('missing_recommended_assets', []))}` |",
            f"| Recommended sets | `{_join_or_none(media_kit.get('available_recommended_sets', []))}` |",
        ]
    )
    bundles = media_kit.get("bundles") if isinstance(media_kit.get("bundles"), list) else []
    if bundles:
        lines.extend(
            [
                "",
                "| Bundle | Kind | Status | Targets | Architectures | Quantization | Assets | Missing recommended assets |",
                "| --- | --- | --- | --- | --- | --- | ---: | --- |",
            ]
        )
        for bundle in bundles:
            if isinstance(bundle, dict):
                lines.append(
                    "| "
                    f"{_markdown_cell(bundle.get('artifact'))} | "
                    f"{_markdown_cell(bundle.get('kind'))} | "
                    f"{_markdown_cell(bundle.get('status'))} | "
                    f"{_markdown_cell(_engine_target_ids_text(bundle.get('engine_targets')))} | "
                    f"{_markdown_cell(_scorecard_group_names_text(bundle.get('architecture_summary'), 'model_architecture'))} | "
                    f"{_markdown_cell(_scorecard_group_names_text(bundle.get('quantization_summary'), 'quantization'))} | "
                    f"{bundle.get('asset_count', 0)} | "
                    f"{_join_or_none(bundle.get('missing_recommended_assets', []))} |"
                )
    else:
        lines.append("No publication bundle media-kit summaries were supplied by claim-readiness evidence.")
    lines.extend(["", "## Agentic Protocol Repair", ""])
    lines.extend(
        [
            "| Field | Value |",
            "| --- | --- |",
            f"| Status | `{_markdown_cell(protocol_repair_summary.get('status'))}` |",
            f"| Scorecard repair cases | `{protocol_repair_summary.get('tool_parser_repairs_valid', 0)}/{protocol_repair_summary.get('tool_parser_repair_cases', 0)} valid` |",
            f"| Scorecard repair valid rate | `{_percent(protocol_repair_summary.get('tool_parser_repair_valid_rate_percent'))}` |",
            f"| Invalid tool calls | `{protocol_repair_summary.get('invalid_tool_call_count', 0)}` |",
            f"| Matrix-gate repair cases | `{protocol_repair_summary.get('matrix_gate_tool_parser_repairs_valid', 0)}/{protocol_repair_summary.get('matrix_gate_tool_parser_repair_cases', 0)} valid` |",
            f"| Matrix-gate invalid tool calls | `{protocol_repair_summary.get('matrix_gate_invalid_tool_call_count', 0)}` |",
            f"| Matrix-gate repair evidence gaps | `{protocol_repair_summary.get('matrix_gate_tool_parser_repair_artifacts_missing', 0)}` |",
        ]
    )
    lines.extend(["", "## Matrix Scorecards", ""])
    if scorecards:
        lines.extend(
            [
                "| Matrix | Targets | Architectures | Quantization | Runs | Cases | Pass rate | Parser repair | Invalid tools | Result artifacts | Telemetry | Concurrency |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for scorecard in scorecards:
            lines.append(
                "| "
                f"{_markdown_cell(scorecard.get('matrix_name'))} | "
                f"{_markdown_cell(_engine_target_ids_text(scorecard.get('engine_targets')))} | "
                f"{_markdown_cell(_scorecard_group_names_text(scorecard.get('architecture_summary'), 'model_architecture'))} | "
                f"{_markdown_cell(_scorecard_group_names_text(scorecard.get('quantization_summary'), 'quantization'))} | "
                f"{scorecard.get('completed_runs', 0)}/{scorecard.get('total_runs', 0)} | "
                f"{scorecard.get('passed_cases', 0)}/{scorecard.get('total_cases', 0)} | "
                f"{_percent(scorecard.get('pass_rate_percent'))} | "
                f"{scorecard.get('tool_parser_repairs_valid', 0)}/{scorecard.get('tool_parser_repair_cases', 0)} | "
                f"{scorecard.get('invalid_tool_call_count', 0)} | "
                f"{scorecard.get('result_artifacts_loaded', 0)}/{scorecard.get('entry_count', 0)} | "
                f"{_markdown_cell(scorecard.get('telemetry_quality'))} | "
                f"{_markdown_cell(scorecard.get('concurrency_evidence'))} |"
            )
    else:
        lines.append("No matrix scorecards supplied.")
    lines.extend(["", "## Top Scorecard Entries", ""])
    top_entries = [entry for scorecard in scorecards for entry in scorecard.get("top_entries", [])]
    if top_entries:
        lines.extend(
            [
                "| Rank | Engine | Model | Suite | Pass rate | Avg latency ms | Decode tok/s |",
                "| ---: | --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for entry in top_entries[:8]:
            lines.append(
                "| "
                f"{entry.get('rank', '')} | "
                f"{_markdown_cell(entry.get('engine'))} | "
                f"{_markdown_cell(entry.get('model'))} | "
                f"{_markdown_cell(entry.get('suite'))} | "
                f"{_percent(entry.get('pass_rate_percent'))} | "
                f"{_number(entry.get('avg_latency_ms'))} | "
                f"{_number(entry.get('avg_decode_tokens_per_second'))} |"
            )
    else:
        lines.append("No leaderboard entries supplied.")
    lines.extend(["", "## Disclosures", ""])
    lines.extend(f"- {_markdown_cell(item)}" for item in report.get("disclosures", []) or ["No disclosures generated."])
    lines.extend(
        [
            "",
            "## Security Boundary",
            "",
            "- This brief excludes raw provider payloads, raw traces, API keys, request headers, keyring values, and dotenv contents.",
            "- Source artifact paths are reduced before inclusion.",
            "- Treat this as a publication signoff aid, not a substitute for rerunning validation.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json_artifact(path: Path | None, *, expected_schema: str | None = None) -> dict[str, Any]:
    if path is None:
        raise ConfigError("missing JSON artifact path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read JSON artifact {path.name}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON artifact {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"JSON artifact {path.name} must contain an object")
    if expected_schema:
        schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema"), payload.get("report_type")) if value}
        if expected_schema not in schema_values:
            raise ConfigError(f"JSON artifact {path.name} must use schema {expected_schema}")
    return payload


def _claim_readiness_summary(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    blocker_categories = _failing_categories(checks, "blocker")
    warning_categories = _failing_categories(checks, "warning")
    return {
        "artifact": _artifact_ref("claim_readiness", path),
        "name": _safe_text(payload.get("name")),
        "ready": payload.get("ready") is True,
        "checks": _int(summary.get("checks")),
        "passed": _int(summary.get("passed")),
        "blockers": _int(summary.get("blockers")),
        "warnings": _int(summary.get("warnings")),
        "blocker_categories": blocker_categories,
        "warning_categories": warning_categories,
    }


def _media_kit_summary(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    bundle_groups = (
        ("run", "publication_bundle_summaries", "run publication bundle"),
        ("matrix", "matrix_publication_bundle_summaries", "matrix publication bundle"),
    )
    bundles: list[dict[str, Any]] = []
    missing_assets: set[str] = set()
    recommended_sets: set[str] = set()
    schema_mismatches = 0
    missing_media_kit_count = 0
    review_status_count = 0
    unsafe_bundles = 0
    asset_count = 0
    run_bundle_count = 0
    matrix_bundle_count = 0
    for kind, key, default_artifact in bundle_groups:
        source = evidence.get(key)
        source_bundles = source if isinstance(source, list) else []
        if kind == "run":
            run_bundle_count = len([item for item in source_bundles if isinstance(item, dict)])
        else:
            matrix_bundle_count = len([item for item in source_bundles if isinstance(item, dict)])
        for index, bundle in enumerate(source_bundles, start=1):
            if not isinstance(bundle, dict):
                continue
            media = bundle.get("media_kit") if isinstance(bundle.get("media_kit"), dict) else {}
            media_present = bool(media)
            missing = _text_list(
                media.get("missing_recommended_assets")
                or media.get("missing_assets")
                or bundle.get("missing_recommended_assets")
                or bundle.get("missing_assets")
            )
            sets = _text_list(media.get("recommended_sets") or media.get("available_recommended_sets") or media.get("recommended_publication_sets"))
            schema_version = _safe_text(media.get("schema_version"))
            schema_ok = not schema_version or schema_version == MEDIA_KIT_SCHEMA_VERSION
            unsafe = _has_unsafe_security_flags(bundle) or _has_unsafe_security_flags(media)
            bundle_asset_count = _int(media.get("asset_count") or media.get("artifact_count") or bundle.get("artifact_count"))
            bundle_status = _safe_text(media.get("status") or bundle.get("status") or media.get("readiness_state") or "unknown") or "unknown"
            status_ok = bundle_status.lower() in {"ready", "pass", "passing", "ok", "complete"}
            missing_assets.update(missing)
            recommended_sets.update(sets)
            asset_count += bundle_asset_count
            schema_mismatches += 0 if schema_ok else 1
            missing_media_kit_count += 0 if media_present else 1
            review_status_count += 0 if status_ok else 1
            unsafe_bundles += 1 if unsafe else 0
            bundles.append(
                {
                    "kind": kind,
                    "artifact": _safe_text(
                        bundle.get("artifact")
                        or bundle.get("bundle")
                        or bundle.get("name")
                        or f"{default_artifact} {index}"
                    ),
                    "status": bundle_status,
                    "schema_version": schema_version,
                    "schema_ok": schema_ok,
                    "asset_count": bundle_asset_count,
                    "engine_targets": _compact_engine_targets(bundle.get("engine_targets")),
                    "architecture_summary": _compact_scorecard_group_summary(
                        bundle.get("architecture_summary"),
                        key="model_architecture",
                    ),
                    "quantization_summary": _compact_scorecard_group_summary(
                        bundle.get("quantization_summary"),
                        key="quantization",
                    ),
                    "missing_recommended_assets": missing,
                    "recommended_sets": sets,
                    "unsafe_security_flags": unsafe,
                }
            )
    bundle_count = len(bundles)
    if bundle_count == 0:
        status = "not-supplied"
    elif missing_assets or schema_mismatches or missing_media_kit_count or review_status_count or unsafe_bundles:
        status = "review-required"
    else:
        status = "ready"
    return {
        "expected_schema_version": MEDIA_KIT_SCHEMA_VERSION,
        "status": status,
        "bundle_count": bundle_count,
        "run_bundle_count": run_bundle_count,
        "matrix_bundle_count": matrix_bundle_count,
        "asset_count": asset_count,
        "missing_recommended_assets": sorted(missing_assets),
        "available_recommended_sets": sorted(recommended_sets),
        "schema_mismatches": schema_mismatches,
        "missing_media_kit_count": missing_media_kit_count,
        "review_status_count": review_status_count,
        "unsafe_bundle_count": unsafe_bundles,
        "bundles": bundles,
    }


def _matrix_scorecard_summary(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    schema_values = {str(value) for value in (payload.get("schema_version"), payload.get("schema"), payload.get("report_type")) if value}
    if MATRIX_SCORECARD_REPORT_TYPE not in schema_values:
        raise ConfigError(f"matrix scorecard {path.name} must use report_type {MATRIX_SCORECARD_REPORT_TYPE}")
    matrix = payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}
    scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else {}
    security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    leaderboard = payload.get("leaderboard") if isinstance(payload.get("leaderboard"), list) else []
    return {
        "artifact": _artifact_ref("matrix_scorecard", path),
        "matrix_name": _safe_text(matrix.get("name")),
        "total_runs": _int(matrix.get("total_runs")),
        "completed_runs": _int(matrix.get("completed_runs")),
        "failed_runs": _int(matrix.get("failed_runs")),
        "entry_count": _int(scorecard.get("entry_count")),
        "total_cases": _int(scorecard.get("total_cases")),
        "passed_cases": _int(scorecard.get("passed_cases")),
        "failed_cases": _int(scorecard.get("failed_cases")),
        "pass_rate_percent": _num(scorecard.get("pass_rate_percent")),
        "invalid_tool_call_count": _int(scorecard.get("invalid_tool_call_count")),
        "tool_parser_repair_cases": _int(scorecard.get("tool_parser_repair_cases")),
        "tool_parser_repairs_valid": _int(scorecard.get("tool_parser_repairs_valid")),
        "tool_parser_repair_valid_rate_percent": _num(scorecard.get("tool_parser_repair_valid_rate_percent")),
        "engine_targets": _compact_engine_targets(scorecard.get("engine_targets") or payload.get("engine_targets")),
        "architecture_summary": _compact_scorecard_group_summary(
            payload.get("architecture_summary"),
            key="model_architecture",
        ),
        "quantization_summary": _compact_scorecard_group_summary(
            payload.get("quantization_summary"),
            key="quantization",
        ),
        "result_artifacts_loaded": _int(scorecard.get("result_artifacts_loaded")),
        "telemetry_quality": _compact_map_text(scorecard.get("telemetry_quality_summary")),
        "stats_comparability": _compact_map_text(scorecard.get("stats_comparability_summary")),
        "concurrency_evidence": _concurrency_text(scorecard.get("concurrency_evidence")),
        "top_entries": [_leaderboard_entry(row) for row in leaderboard[:5] if isinstance(row, dict)],
        "security": {
            "contains_raw_provider_payloads": security.get("contains_raw_provider_payloads") is True,
            "contains_secrets": security.get("contains_secrets") is True,
        },
    }


def _protocol_repair_summary(claim_payload: dict[str, Any], scorecards: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = claim_payload.get("evidence") if isinstance(claim_payload.get("evidence"), dict) else {}
    scorecard_sources = scorecards
    if not scorecard_sources:
        summaries = evidence.get("matrix_scorecard_summaries")
        scorecard_sources = [item for item in summaries if isinstance(item, dict)] if isinstance(summaries, list) else []
    invalid_tool_call_count = sum(_int(item.get("invalid_tool_call_count")) for item in scorecard_sources)
    repair_cases = sum(_int(item.get("tool_parser_repair_cases")) for item in scorecard_sources)
    repairs_valid = sum(_int(item.get("tool_parser_repairs_valid")) for item in scorecard_sources)
    gate = (
        evidence.get("matrix_gate_tool_parser_repair_summary")
        if isinstance(evidence.get("matrix_gate_tool_parser_repair_summary"), dict)
        else {}
    )
    gate_invalid = _int(gate.get("invalid_tool_call_count"))
    gate_cases = _int(gate.get("tool_parser_repair_cases"))
    gate_valid = _int(gate.get("tool_parser_repairs_valid"))
    gate_missing = _int(evidence.get("matrix_gate_tool_parser_repair_artifacts_missing"))
    if repair_cases == 0 and gate_cases == 0:
        status = "no-evidence"
    elif invalid_tool_call_count or gate_invalid or repairs_valid < repair_cases or gate_valid < gate_cases or gate_missing:
        status = "review-required"
    else:
        status = "ready"
    return {
        "status": status,
        "source_scorecard_count": len(scorecard_sources),
        "invalid_tool_call_count": invalid_tool_call_count,
        "tool_parser_repair_cases": repair_cases,
        "tool_parser_repairs_valid": repairs_valid,
        "tool_parser_repair_valid_rate_percent": round((repairs_valid / repair_cases) * 100, 3)
        if repair_cases
        else 0.0,
        "matrix_gate_invalid_tool_call_count": gate_invalid,
        "matrix_gate_tool_parser_repair_cases": gate_cases,
        "matrix_gate_tool_parser_repairs_valid": gate_valid,
        "matrix_gate_tool_parser_repair_valid_rate_percent": round((gate_valid / gate_cases) * 100, 3)
        if gate_cases
        else 0.0,
        "matrix_gate_tool_parser_repair_artifacts_missing": gate_missing,
    }


def _release_provenance_summary(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    packaging = payload.get("packaging_readiness") if isinstance(payload.get("packaging_readiness"), dict) else {}
    sbom = payload.get("sbom") if isinstance(payload.get("sbom"), dict) else {}
    return {
        "artifact": _artifact_ref("release_provenance", path),
        "schema_version": _safe_text(payload.get("schema_version")),
        "packaging_ok": packaging.get("ok"),
        "packaging_status": _safe_text(packaging.get("status")),
        "sbom_package_count": _int(sbom.get("package_count") or len(sbom.get("packages", []) if isinstance(sbom.get("packages"), list) else [])),
    }


def _evidence_index_summary(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    return {
        "artifact": _artifact_ref("evidence_index", path),
        "name": _safe_text(payload.get("name")),
        "artifact_count": _int(payload.get("artifact_count")),
        "readiness_state": _safe_text(readiness.get("state")),
        "ready": readiness.get("ready"),
    }


def _proof_points(
    claim_summary: dict[str, Any],
    claim_payload: dict[str, Any],
    scorecards: list[dict[str, Any]],
    release_summary: dict[str, Any] | None,
    evidence_summary: dict[str, Any] | None,
    media_kit: dict[str, Any],
    protocol_repair_summary: dict[str, Any],
) -> list[str]:
    points = [
        f"Claim-readiness checks passed {claim_summary['passed']} of {claim_summary['checks']} with {claim_summary['blockers']} blocker(s).",
    ]
    if scorecards:
        total_cases = sum(_int(item.get("total_cases")) for item in scorecards)
        passed_cases = sum(_int(item.get("passed_cases")) for item in scorecards)
        points.append(f"Matrix scorecards cover {passed_cases}/{total_cases} passing cases across {len(scorecards)} supplied scorecard artifact(s).")
    evidence = claim_payload.get("evidence") if isinstance(claim_payload.get("evidence"), dict) else {}
    contract = evidence.get("provider_contract_capability_evidence") if isinstance(evidence.get("provider_contract_capability_evidence"), dict) else {}
    direct = contract.get("directly_checked") if isinstance(contract.get("directly_checked"), list) else []
    if direct:
        points.append(f"Provider contract evidence directly checks: {', '.join(str(item) for item in direct)}.")
    if release_summary:
        points.append("Release provenance was supplied, including packaging/SBOM summary metadata.")
    if evidence_summary:
        points.append(f"Evidence index state is {evidence_summary.get('readiness_state') or 'unknown'}.")
    if media_kit.get("bundle_count"):
        points.append(
            "Media-kit evidence covers "
            f"{media_kit.get('asset_count', 0)} publication asset(s) across {media_kit.get('bundle_count', 0)} bundle summary artifact(s)."
        )
    if protocol_repair_summary.get("tool_parser_repair_cases"):
        points.append(
            "Protocol-repair scorecards report "
            f"{protocol_repair_summary.get('tool_parser_repairs_valid', 0)}/"
            f"{protocol_repair_summary.get('tool_parser_repair_cases', 0)} valid parser-repair cases "
            f"with {protocol_repair_summary.get('invalid_tool_call_count', 0)} invalid tool-call emission(s)."
        )
    return points


def _disclosures(
    claim_summary: dict[str, Any],
    claim_payload: dict[str, Any],
    scorecards: list[dict[str, Any]],
    release_summary: dict[str, Any] | None,
    evidence_summary: dict[str, Any] | None,
    media_kit: dict[str, Any],
    protocol_repair_summary: dict[str, Any],
) -> list[str]:
    disclosures: list[str] = []
    if not claim_summary["ready"]:
        disclosures.append(f"Do not publish external benchmark claims until blocker categories are resolved: {_join_or_none(claim_summary['blocker_categories'])}.")
    if claim_summary["warning_categories"]:
        disclosures.append(f"Publication requires human review of warning categories: {_join_or_none(claim_summary['warning_categories'])}.")
    evidence = claim_payload.get("evidence") if isinstance(claim_payload.get("evidence"), dict) else {}
    contract = evidence.get("provider_contract_capability_evidence") if isinstance(evidence.get("provider_contract_capability_evidence"), dict) else {}
    not_covered = contract.get("not_covered_counts") if isinstance(contract.get("not_covered_counts"), dict) else {}
    if not_covered:
        disclosures.append(f"Capabilities not covered by provider contract checks: {_compact_map_text(not_covered)}.")
    for scorecard in scorecards:
        if scorecard.get("failed_runs"):
            disclosures.append(f"Matrix {scorecard.get('matrix_name') or 'unknown'} contains {scorecard['failed_runs']} failed run(s).")
        if scorecard.get("result_artifacts_loaded") != scorecard.get("entry_count"):
            disclosures.append(
                f"Matrix {scorecard.get('matrix_name') or 'unknown'} loaded result artifacts for {scorecard.get('result_artifacts_loaded')}/{scorecard.get('entry_count')} entries."
            )
        if scorecard.get("security", {}).get("contains_raw_provider_payloads") or scorecard.get("security", {}).get("contains_secrets"):
            disclosures.append(f"Matrix scorecard {scorecard.get('matrix_name') or 'unknown'} reports unsafe security flags.")
    if protocol_repair_summary.get("status") == "no-evidence":
        disclosures.append("No protocol-repair scorecard or matrix-gate evidence was summarized for publication.")
    elif protocol_repair_summary.get("status") != "ready":
        disclosures.append(
            "Protocol-repair evidence requires review: "
            f"{protocol_repair_summary.get('tool_parser_repairs_valid', 0)}/"
            f"{protocol_repair_summary.get('tool_parser_repair_cases', 0)} scorecard cases valid, "
            f"{protocol_repair_summary.get('invalid_tool_call_count', 0)} invalid tool-call emission(s), "
            f"{protocol_repair_summary.get('matrix_gate_tool_parser_repair_artifacts_missing', 0)} matrix-gate evidence gap(s)."
        )
    if release_summary and release_summary.get("packaging_ok") is False:
        disclosures.append("Release provenance packaging readiness is not passing.")
    if evidence_summary and evidence_summary.get("ready") is False:
        disclosures.append(f"Evidence index is not ready: {evidence_summary.get('readiness_state') or 'unknown'}.")
    if media_kit.get("status") == "not-supplied":
        disclosures.append("No publication bundle media-kit evidence was summarized by claim-readiness; prepare media assets before external distribution.")
    elif media_kit.get("status") != "ready":
        if media_kit.get("missing_recommended_assets"):
            disclosures.append(f"Media kit requires review for missing recommended assets: {_join_or_none(media_kit['missing_recommended_assets'])}.")
        if media_kit.get("schema_mismatches"):
            disclosures.append(f"Media kit contains {media_kit['schema_mismatches']} schema mismatch(es).")
        if media_kit.get("missing_media_kit_count"):
            disclosures.append(f"Media kit evidence is missing from {media_kit['missing_media_kit_count']} publication bundle summary artifact(s).")
        if media_kit.get("review_status_count"):
            disclosures.append(f"Media kit contains {media_kit['review_status_count']} bundle summary status(es) that are not ready.")
        if media_kit.get("unsafe_bundle_count"):
            disclosures.append(f"Media kit contains {media_kit['unsafe_bundle_count']} bundle(s) with unsafe security flags.")
    return disclosures or ["No blockers were summarized by the supplied claim-readiness evidence. Keep raw logs and traces out of external materials."]


def _recommended_language(name: str, claim_summary: dict[str, Any], disclosures: list[str]) -> dict[str, str]:
    if claim_summary["ready"]:
        return {
            "headline": f"{name}: AgentBlaster evidence is ready for external review",
            "short_summary": (
                f"AgentBlaster found no publication blockers across {claim_summary['checks']} readiness checks. "
                "Use the supplied scorecards and disclosures when making model, engine, or throughput claims."
            ),
            "caveat": disclosures[0] if disclosures else "Disclose model revisions, quantization, telemetry coverage, and concurrency settings.",
        }
    return {
        "headline": f"{name}: AgentBlaster evidence is not ready for publication",
        "short_summary": (
            f"AgentBlaster found {claim_summary['blockers']} blocker(s) and {claim_summary['warnings']} warning(s). "
            "Do not publish comparative claims until blockers are remediated and the readiness gate is rerun."
        ),
        "caveat": disclosures[0] if disclosures else "Resolve missing or failed evidence before publication.",
    }


def _leaderboard_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": _int(row.get("rank")),
        "engine": _safe_text(row.get("engine")),
        "provider": _safe_text(row.get("provider")),
        "model": _safe_text(row.get("model")),
        "suite": _safe_text(row.get("suite")),
        "pass_rate_percent": _num(row.get("pass_rate_percent")),
        "avg_latency_ms": _num(row.get("avg_latency_ms")),
        "avg_ttft_ms": _num(row.get("avg_ttft_ms")),
        "avg_decode_tokens_per_second": _num(row.get("avg_decode_tokens_per_second")),
    }


def _brief_engine_targets(
    claim_payload: dict[str, Any],
    scorecards: list[dict[str, Any]],
    media_kit: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    for scorecard in scorecards:
        candidates.extend(scorecard.get("engine_targets") if isinstance(scorecard.get("engine_targets"), list) else [])
    bundles = media_kit.get("bundles") if isinstance(media_kit.get("bundles"), list) else []
    for bundle in bundles:
        if isinstance(bundle, dict) and isinstance(bundle.get("engine_targets"), list):
            candidates.extend(bundle["engine_targets"])
    evidence = claim_payload.get("evidence") if isinstance(claim_payload.get("evidence"), dict) else {}
    for key in ("matrix_scorecard_summaries", "matrix_publication_bundle_summaries"):
        summaries = evidence.get(key)
        if not isinstance(summaries, list):
            continue
        for summary in summaries:
            if isinstance(summary, dict) and isinstance(summary.get("engine_targets"), list):
                candidates.extend(summary["engine_targets"])
    return _compact_engine_targets(candidates)


def _brief_scorecard_group_summary(
    claim_payload: dict[str, Any],
    scorecards: list[dict[str, Any]],
    media_kit: dict[str, Any],
    source_field: str,
    *,
    key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_rows(value: Any) -> None:
        for row in _compact_scorecard_group_summary(value, key=key):
            group = _safe_text(row.get(key))
            if not group or group in seen:
                continue
            seen.add(group)
            rows.append(row)

    for scorecard in scorecards:
        append_rows(scorecard.get(source_field))
    bundles = media_kit.get("bundles") if isinstance(media_kit.get("bundles"), list) else []
    for bundle in bundles:
        if isinstance(bundle, dict):
            append_rows(bundle.get(source_field))
    evidence = claim_payload.get("evidence") if isinstance(claim_payload.get("evidence"), dict) else {}
    for evidence_key in ("matrix_scorecard_summaries", "matrix_publication_bundle_summaries"):
        summaries = evidence.get(evidence_key)
        if not isinstance(summaries, list):
            continue
        for summary in summaries:
            if isinstance(summary, dict):
                append_rows(summary.get(source_field))
    return rows[:12]


def _compact_engine_targets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        target_id = _safe_text(item.get("id"))
        if not target_id or target_id in seen:
            continue
        seen.add(target_id)
        targets.append(
            {
                "id": target_id,
                "display_name": _safe_text(item.get("display_name")),
                "primary_scoring_contract": _safe_text(item.get("primary_scoring_contract")),
            }
        )
    return targets[:12]


def _compact_scorecard_group_summary(value: Any, *, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                key: _safe_text(item.get(key) or "unknown"),
                "runs": _int(item.get("runs")),
                "failed_runs": _int(item.get("failed_runs")),
                "completed_runs": _int(item.get("completed_runs")),
                "result_artifacts_loaded": _int(item.get("result_artifacts_loaded")),
                "total_cases": _int(item.get("total_cases")),
                "passed": _int(item.get("passed")),
                "failed": _int(item.get("failed")),
                "pass_rate_percent": _num(item.get("pass_rate_percent")),
                "avg_latency_ms": _num(item.get("avg_latency_ms")),
                "avg_decode_tokens_per_second": _num(item.get("avg_decode_tokens_per_second")),
                "judge_rubric_cases": _int(item.get("judge_rubric_cases")),
                "judge_verdicts_valid": _int(item.get("judge_verdicts_valid")),
                "invalid_tool_call_count": _int(item.get("invalid_tool_call_count")),
                "tool_parser_repair_cases": _int(item.get("tool_parser_repair_cases")),
                "tool_parser_repairs_valid": _int(item.get("tool_parser_repairs_valid")),
                "tool_parser_repair_valid_rate_percent": _num(item.get("tool_parser_repair_valid_rate_percent")),
            }
        )
    return rows[:12]


def _engine_target_ids_text(value: Any) -> str:
    targets = _compact_engine_targets(value)
    if not targets:
        return "none"
    return ", ".join(str(item["id"]) for item in targets)


def _scorecard_group_names_text(value: Any, key: str) -> str:
    rows = _compact_scorecard_group_summary(value, key=key)
    if not rows:
        return "none"
    return ", ".join(str(row[key]) for row in rows)


def _protocol_repair_status_text(value: dict[str, Any]) -> str:
    status = _safe_text(value.get("status")) or "unknown"
    return (
        f"{status}; scorecard={value.get('tool_parser_repairs_valid', 0)}/"
        f"{value.get('tool_parser_repair_cases', 0)}; "
        f"invalid={value.get('invalid_tool_call_count', 0)}; "
        f"gate={value.get('matrix_gate_tool_parser_repairs_valid', 0)}/"
        f"{value.get('matrix_gate_tool_parser_repair_cases', 0)}"
    )


def _failing_categories(checks: list[Any], severity: str) -> list[str]:
    categories = {
        _safe_text(check.get("category"))
        for check in checks
        if isinstance(check, dict) and check.get("severity") == severity and check.get("ok") is not True
    }
    return sorted(item for item in categories if item)


def _artifact_ref(kind: str, path: Path) -> dict[str, Any]:
    path_text = str(path)
    path_redacted = path.is_absolute() or ".." in path.parts
    return {
        "kind": kind,
        "artifact": path.name if path_redacted else path_text,
        "path_redacted": path_redacted,
    }


def _safe_name(value: str) -> str:
    text = _safe_text(value)
    return re.sub(r"[^A-Za-z0-9_. -]+", "-", text).strip() or "benchmark-claim"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()[:240]


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|") or "none"


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> str:
    number = _num(value)
    return "n/a" if number is None else f"{number:.2f}"


def _percent(value: Any) -> str:
    number = _num(value)
    return "n/a" if number is None else f"{number:.2f}%"


def _compact_map_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ", ".join(f"{_safe_text(key)}={_safe_text(item)}" for key, item in sorted(value.items()))


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = _safe_text(item.get("name") or item.get("role") or item.get("asset") or item.get("id") or item.get("type"))
        else:
            text = _safe_text(item)
        if text:
            values.append(text)
    return sorted(set(values))


def _has_unsafe_security_flags(value: dict[str, Any]) -> bool:
    security = value.get("security") if isinstance(value.get("security"), dict) else value
    return any(
        security.get(flag) is True
        for flag in (
            "contains_raw_provider_payloads",
            "contains_raw_traces",
            "contains_secrets",
            "contains_api_keys",
            "contains_request_headers",
        )
    )


def _media_kit_status_text(media_kit: dict[str, Any]) -> str:
    status = _safe_text(media_kit.get("status")) or "unknown"
    return f"{status}; {media_kit.get('bundle_count', 0)} bundle(s); {len(media_kit.get('missing_recommended_assets', []) or [])} missing recommended asset(s)"


def _concurrency_text(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    levels = value.get("concurrency_levels")
    if isinstance(levels, list) and levels:
        return f"levels={','.join(str(item) for item in levels)}"
    return _compact_map_text(value)


def _join_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none"
