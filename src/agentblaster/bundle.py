from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from agentblaster.errors import ConfigError
from agentblaster.integrity import (
    INTEGRITY_FILENAME,
    SIGNATURE_FILENAME,
    load_integrity_manifest,
    load_signature_manifest,
    verify_run_integrity,
)


FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PUBLICATION_BUNDLE_MANIFEST = "publication-bundle-manifest.json"
MATRIX_PUBLICATION_BUNDLE_MANIFEST = "matrix-publication-bundle-manifest.json"
MEDIA_KIT_SCHEMA_VERSION = "agentblaster.media-kit.v1"
MATRIX_PUBLICATION_BUNDLE_SCHEMA_VERSION = "agentblaster.matrix-publication-bundle.v1"
PUBLICATION_BUNDLE_ARTIFACTS = {
    "manifest.json",
    "suite.json",
    "summary.json",
    "report.html",
    "report.md",
    "report.pdf",
    "publication.json",
    "report-card.svg",
    "report-card.png",
    INTEGRITY_FILENAME,
    SIGNATURE_FILENAME,
}
MATRIX_PUBLICATION_REPORT_SUFFIXES = (
    "matrix-report.html",
    "matrix-report.md",
    "matrix-report.json",
    "matrix-report.pdf",
    "matrix-scorecard.html",
    "matrix-scorecard.md",
    "matrix-scorecard.json",
    "matrix-scorecard.svg",
    "matrix-scorecard.png",
    "matrix-scorecard.pdf",
)


def create_replay_bundle(
    run_dir: Path,
    *,
    output_dir: Path | None = None,
    strict: bool = False,
) -> Path:
    """Create a deterministic portable bundle from a verified run directory."""
    verification = verify_run_integrity(run_dir, allow_extra=not strict)
    if not verification.ok:
        details = []
        if verification.missing:
            details.append(f"missing={','.join(verification.missing)}")
        if verification.changed:
            details.append(f"changed={','.join(verification.changed)}")
        if verification.extra:
            details.append(f"extra={','.join(verification.extra)}")
        raise ConfigError(f"run integrity verification failed: {'; '.join(details)}")

    integrity = load_integrity_manifest(run_dir)
    target_dir = output_dir or run_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{integrity.run_id}.agentblaster.zip"

    archive_paths = sorted([INTEGRITY_FILENAME, *integrity.artifacts.keys()])
    if (run_dir / SIGNATURE_FILENAME).exists():
        archive_paths.append(SIGNATURE_FILENAME)
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for relative_path in archive_paths:
            source = _safe_artifact_path(run_dir, relative_path)
            _write_deterministic_file(archive, source, relative_path)

    return target


def create_publication_bundle(
    run_dir: Path,
    *,
    output_dir: Path | None = None,
) -> Path:
    """Create a deterministic shareable bundle containing only redacted publication artifacts."""
    verification = verify_run_integrity(run_dir, allow_extra=True)
    if not verification.ok:
        details = []
        if verification.missing:
            details.append(f"missing={','.join(verification.missing)}")
        if verification.changed:
            details.append(f"changed={','.join(verification.changed)}")
        raise ConfigError(f"run integrity verification failed: {'; '.join(details)}")

    integrity = load_integrity_manifest(run_dir)
    target_dir = output_dir or run_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{integrity.run_id}.agentblaster-publication.zip"
    archive_paths = sorted(
        artifact
        for artifact in PUBLICATION_BUNDLE_ARTIFACTS
        if (run_dir / artifact).exists()
    )
    if "publication.json" not in archive_paths:
        raise ConfigError("publication bundle requires publication.json; run `agentblaster report --format publication` first")

    publication_payload = _load_publication_payload(run_dir)
    signature_summary = _publication_signature_summary(run_dir, integrity, archive_paths)
    bundle_manifest = _publication_bundle_manifest(integrity.run_id, archive_paths, publication_payload, signature_summary)

    generated_jsons = {PUBLICATION_BUNDLE_MANIFEST: bundle_manifest}
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for relative_path in sorted([*archive_paths, *generated_jsons]):
            if relative_path in generated_jsons:
                _write_deterministic_json(archive, relative_path, generated_jsons[relative_path])
                continue
            source = _safe_artifact_path(run_dir, relative_path)
            _write_deterministic_file(archive, source, relative_path)
    return target


def create_matrix_publication_bundle(
    summary_json: Path,
    *,
    report_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Create a deterministic shareable bundle containing matrix report and scorecard artifacts."""
    if not summary_json.exists() or not summary_json.is_file():
        raise ConfigError(f"missing matrix summary: {summary_json}")

    source_dir = report_dir or summary_json.parent
    stem = summary_json.stem
    required_scorecard = source_dir / f"{stem}-matrix-scorecard.json"
    if not required_scorecard.exists():
        raise ConfigError(
            "matrix publication bundle requires matrix scorecard JSON; "
            "run `agentblaster matrix scorecard --format json,card` first"
        )
    scorecard_payload = _load_matrix_scorecard_payload(required_scorecard)

    archive_sources: list[tuple[Path, str]] = [(summary_json, summary_json.name)]
    for suffix in MATRIX_PUBLICATION_REPORT_SUFFIXES:
        path = source_dir / f"{stem}-{suffix}"
        if path.exists() and path.is_file():
            archive_sources.append((path, path.name))

    target_dir = output_dir or source_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}.agentblaster-matrix-publication.zip"
    archive_paths = sorted(relative_path for _, relative_path in archive_sources)
    bundle_manifest = _matrix_publication_bundle_manifest(
        stem,
        summary_json.name,
        archive_paths,
        engine_targets=_matrix_publication_engine_targets(scorecard_payload),
        architecture_summary=_compact_scorecard_group_summary(
            scorecard_payload.get("architecture_summary"),
            key="model_architecture",
        ),
        quantization_summary=_compact_scorecard_group_summary(
            scorecard_payload.get("quantization_summary"),
            key="quantization",
        ),
    )
    sources_by_name = {relative_path: source for source, relative_path in archive_sources}
    generated_jsons = {MATRIX_PUBLICATION_BUNDLE_MANIFEST: bundle_manifest}
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for relative_path in sorted([*sources_by_name, *generated_jsons]):
            if relative_path in generated_jsons:
                _write_deterministic_json(archive, relative_path, generated_jsons[relative_path])
                continue
            _write_deterministic_file(archive, sources_by_name[relative_path], relative_path)
    return target


def _safe_artifact_path(run_dir: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"unsafe artifact path in integrity manifest: {relative_path}")
    source = run_dir / path
    if not source.exists():
        raise ConfigError(f"missing artifact for replay bundle: {relative_path}")
    return source


def _write_deterministic_file(archive: ZipFile, source: Path, relative_path: str) -> None:
    info = ZipInfo(relative_path, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, source.read_bytes())


def _write_deterministic_json(archive: ZipFile, relative_path: str, payload: dict[str, object]) -> None:
    info = ZipInfo(relative_path, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    archive.writestr(info, body)


def _load_publication_payload(run_dir: Path) -> dict[str, object]:
    try:
        payload = json.loads((run_dir / "publication.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid publication.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("publication.json must contain an object")
    return payload


def _load_matrix_scorecard_payload(scorecard_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(scorecard_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid matrix scorecard JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("matrix scorecard JSON must contain an object")
    return payload


def _publication_bundle_manifest(
    run_id: str,
    archive_paths: list[str],
    publication_payload: dict[str, object],
    signature_summary: dict[str, object],
) -> dict[str, object]:
    readiness = publication_payload.get("publication_readiness")
    if not isinstance(readiness, dict):
        readiness = None
    return {
        "schema_version": "agentblaster.publication-bundle.v1",
        "run_id": run_id,
        "artifact_count": len(archive_paths),
        "artifacts": archive_paths,
        "publication_readiness": readiness,
        "media_kit": _run_media_kit_manifest(run_id, archive_paths),
        "integrity": {
            "integrity_manifest_present": INTEGRITY_FILENAME in archive_paths,
            "signature_manifest_present": SIGNATURE_FILENAME in archive_paths,
            **signature_summary,
        },
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": False,
            "notes": (
                "Publication bundle manifest is derived from allowlisted publication artifacts and excludes raw "
                "traces, provider payloads, API keys, request headers, exports, caches, and results.jsonl."
            ),
        },
    }


def _matrix_publication_bundle_manifest(
    stem: str,
    summary_artifact: str,
    archive_paths: list[str],
    *,
    engine_targets: list[dict[str, object]],
    architecture_summary: list[dict[str, object]],
    quantization_summary: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": MATRIX_PUBLICATION_BUNDLE_SCHEMA_VERSION,
        "matrix": {
            "artifact_stem": stem,
            "summary_artifact": summary_artifact,
            "scorecard_artifact": f"{stem}-matrix-scorecard.json",
        },
        "engine_targets": engine_targets,
        "architecture_summary": architecture_summary,
        "quantization_summary": quantization_summary,
        "artifact_count": len(archive_paths),
        "artifacts": archive_paths,
        "media_kit": _matrix_media_kit_manifest(stem, archive_paths),
        "security": {
            "contains_raw_secrets": False,
            "contains_raw_provider_payloads": False,
            "contains_results_jsonl": False,
            "contains_per_run_raw_traces": False,
            "notes": (
                "Matrix publication bundle manifest is derived from packaged matrix reports and scorecards. "
                "It excludes per-run results.jsonl, raw traces, provider payloads, exports, API keys, and request headers."
            ),
        },
    }


def _matrix_publication_engine_targets(scorecard_payload: dict[str, object]) -> list[dict[str, object]]:
    scorecard = scorecard_payload.get("scorecard")
    candidates: object = None
    if isinstance(scorecard, dict):
        candidates = scorecard.get("engine_targets")
    if candidates is None:
        candidates = scorecard_payload.get("engine_targets")
    targets = _compact_engine_targets(candidates)
    if targets:
        return targets
    if isinstance(scorecard, dict):
        return _compact_engine_targets_from_entries(scorecard.get("entries"))
    return []


def _compact_engine_targets_from_entries(entries: object) -> list[dict[str, object]]:
    if not isinstance(entries, list):
        return []
    candidates: list[object] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if "engine_target" in entry:
            candidates.append(entry["engine_target"])
        elif "engine_target_id" in entry:
            candidates.append(entry["engine_target_id"])
    return _compact_engine_targets(candidates)


def _compact_engine_targets(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    targets: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        target = _compact_engine_target(item)
        if target is None:
            continue
        target_id = str(target["id"])
        if target_id in seen:
            continue
        seen.add(target_id)
        targets.append(target)
    return targets


def _compact_engine_target(value: object) -> dict[str, object] | None:
    if isinstance(value, str):
        target_id = value.strip()
        if not target_id:
            return None
        return {"id": target_id}
    if not isinstance(value, dict):
        return None
    raw_id = value.get("id") or value.get("engine_target_id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None
    target: dict[str, object] = {"id": raw_id.strip()}
    for key in ("display_name", "primary_scoring_contract"):
        raw_value = value.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            target[key] = raw_value.strip()
    return target


def _compact_scorecard_group_summary(value: object, *, key: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                key: str(item.get(key) or "unknown"),
                "runs": _non_negative_int(item.get("runs")),
                "failed_runs": _non_negative_int(item.get("failed_runs")),
                "completed_runs": _non_negative_int(item.get("completed_runs")),
                "result_artifacts_loaded": _non_negative_int(item.get("result_artifacts_loaded")),
                "total_cases": _non_negative_int(item.get("total_cases")),
                "passed": _non_negative_int(item.get("passed")),
                "failed": _non_negative_int(item.get("failed")),
                "pass_rate_percent": _number_or_none(item.get("pass_rate_percent")),
                "avg_latency_ms": _number_or_none(item.get("avg_latency_ms")),
                "avg_decode_tokens_per_second": _number_or_none(item.get("avg_decode_tokens_per_second")),
                "judge_rubric_cases": _non_negative_int(item.get("judge_rubric_cases")),
                "judge_verdicts_valid": _non_negative_int(item.get("judge_verdicts_valid")),
                "invalid_tool_call_count": _non_negative_int(item.get("invalid_tool_call_count")),
                "tool_parser_repair_cases": _non_negative_int(item.get("tool_parser_repair_cases")),
                "tool_parser_repairs_valid": _non_negative_int(item.get("tool_parser_repairs_valid")),
                "tool_parser_repair_valid_rate_percent": _number_or_none(
                    item.get("tool_parser_repair_valid_rate_percent")
                ),
            }
        )
    return rows[:12]


def _non_negative_int(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _number_or_none(value: object) -> float | int | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _run_media_kit_manifest(run_id: str, archive_paths: list[str]) -> dict[str, object]:
    artifacts = set(archive_paths)
    assets = [
        _media_asset(
            "publication.json",
            artifacts,
            role="structured-run-evidence",
            title="Structured publication payload",
            media_type="application/json",
            audiences=("automation", "corporate-review"),
            usage="Feed dashboards, release-readiness checks, and publication brief generation.",
            required=True,
        ),
        _media_asset(
            "summary.json",
            artifacts,
            role="automation-summary",
            title="Compact run summary",
            media_type="application/json",
            audiences=("automation", "corporate-review"),
            usage="Use for lightweight run identity, pass/fail, and timing summaries.",
            required=True,
        ),
        _media_asset(
            "report.pdf",
            artifacts,
            role="executive-summary",
            title="Executive PDF report",
            media_type="application/pdf",
            audiences=("executive", "corporate-review"),
            usage="Attach to corporate review packets and stakeholder updates.",
            required=True,
        ),
        _media_asset(
            "report.html",
            artifacts,
            role="interactive-report",
            title="HTML engineering report",
            media_type="text/html",
            audiences=("engineering", "corporate-review"),
            usage="Open locally for detailed normalized metrics without raw provider payloads.",
        ),
        _media_asset(
            "report.md",
            artifacts,
            role="markdown-report",
            title="Markdown report",
            media_type="text/markdown",
            audiences=("engineering", "documentation"),
            usage="Paste into issues, PRs, internal notes, or release docs.",
        ),
        _media_asset(
            "report-card.svg",
            artifacts,
            role="social-card-vector",
            title="SVG media card",
            media_type="image/svg+xml",
            audiences=("media", "slides", "corporate-review"),
            usage="Use as the primary editable 1200x630 card for decks and social posts.",
            dimensions="1200x630",
            required=True,
        ),
        _media_asset(
            "report-card.png",
            artifacts,
            role="social-card-raster",
            title="PNG media card",
            media_type="image/png",
            audiences=("media", "slides"),
            usage="Use for image-first media platforms when SVG is not accepted.",
            dimensions="1200x630",
        ),
    ]
    return _media_kit_manifest(
        subject={"type": "run", "run_id": run_id},
        assets=assets,
        recommended_sets=(
            {
                "name": "corporate-review-packet",
                "artifacts": ("publication.json", "summary.json", "report.pdf", "report-card.svg"),
            },
            {
                "name": "media-post-packet",
                "artifacts": ("publication.json", "report-card.svg", "report-card.png"),
            },
        ),
    )


def _matrix_media_kit_manifest(stem: str, archive_paths: list[str]) -> dict[str, object]:
    artifacts = set(archive_paths)
    assets = [
        _media_asset(
            f"{stem}.json",
            artifacts,
            role="matrix-execution-summary",
            title="Matrix execution summary",
            media_type="application/json",
            audiences=("automation", "corporate-review"),
            usage="Use as the campaign-level source artifact for matrix identity and run coverage.",
            required=True,
        ),
        _media_asset(
            f"{stem}-matrix-report.json",
            artifacts,
            role="structured-matrix-report",
            title="Structured matrix report",
            media_type="application/json",
            audiences=("automation", "corporate-review"),
            usage="Feed downstream dashboards and release-evidence indexes.",
        ),
        _media_asset(
            f"{stem}-matrix-scorecard.json",
            artifacts,
            role="structured-scorecard",
            title="Structured matrix scorecard",
            media_type="application/json",
            audiences=("automation", "corporate-review"),
            usage="Use for leaderboard, telemetry-quality, and concurrency-evidence claims.",
            required=True,
        ),
        _media_asset(
            f"{stem}-matrix-report.pdf",
            artifacts,
            role="executive-matrix-report",
            title="Matrix PDF report",
            media_type="application/pdf",
            audiences=("executive", "corporate-review"),
            usage="Attach to matrix campaign review packets.",
        ),
        _media_asset(
            f"{stem}-matrix-scorecard.pdf",
            artifacts,
            role="executive-scorecard",
            title="Matrix scorecard PDF",
            media_type="application/pdf",
            audiences=("executive", "corporate-review"),
            usage="Use as a concise leaderboard review packet.",
            required=True,
        ),
        _media_asset(
            f"{stem}-matrix-scorecard.svg",
            artifacts,
            role="scorecard-card-vector",
            title="Matrix SVG scorecard card",
            media_type="image/svg+xml",
            audiences=("media", "slides", "corporate-review"),
            usage="Use as the primary editable matrix scorecard card for decks and social posts.",
            dimensions="1200x630",
            required=True,
        ),
        _media_asset(
            f"{stem}-matrix-scorecard.png",
            artifacts,
            role="scorecard-card-raster",
            title="Matrix PNG scorecard card",
            media_type="image/png",
            audiences=("media", "slides"),
            usage="Use for image-first media platforms when SVG is not accepted.",
            dimensions="1200x630",
        ),
    ]
    return _media_kit_manifest(
        subject={"type": "matrix", "artifact_stem": stem},
        assets=assets,
        recommended_sets=(
            {
                "name": "corporate-review-packet",
                "artifacts": (
                    f"{stem}.json",
                    f"{stem}-matrix-scorecard.json",
                    f"{stem}-matrix-scorecard.pdf",
                    f"{stem}-matrix-scorecard.svg",
                ),
            },
            {
                "name": "media-post-packet",
                "artifacts": (
                    f"{stem}-matrix-scorecard.json",
                    f"{stem}-matrix-scorecard.svg",
                    f"{stem}-matrix-scorecard.png",
                ),
            },
        ),
    )


def _media_asset(
    artifact: str,
    artifacts: set[str],
    *,
    role: str,
    title: str,
    media_type: str,
    audiences: tuple[str, ...],
    usage: str,
    dimensions: str | None = None,
    required: bool = False,
) -> dict[str, object]:
    asset: dict[str, object] = {
        "artifact": artifact,
        "present": artifact in artifacts,
        "role": role,
        "title": title,
        "media_type": media_type,
        "audiences": list(audiences),
        "usage": usage,
        "required_for_professional_pack": required,
    }
    if dimensions is not None:
        asset["dimensions"] = dimensions
    return asset


def _media_kit_manifest(
    *,
    subject: dict[str, object],
    assets: list[dict[str, object]],
    recommended_sets: tuple[dict[str, object], ...],
) -> dict[str, object]:
    available = {str(asset["artifact"]) for asset in assets if asset["present"]}
    resolved_sets = []
    for artifact_set in recommended_sets:
        artifacts = tuple(str(item) for item in artifact_set["artifacts"])
        missing = [artifact for artifact in artifacts if artifact not in available]
        resolved_sets.append(
            {
                "name": artifact_set["name"],
                "artifacts": list(artifacts),
                "available": not missing,
                "missing_artifacts": missing,
            }
        )
    return {
        "schema_version": MEDIA_KIT_SCHEMA_VERSION,
        "subject": subject,
        "audiences": ["media", "executive", "corporate-review", "automation"],
        "asset_count": len(available),
        "assets": assets,
        "missing_recommended_assets": [
            str(asset["artifact"])
            for asset in assets
            if asset["required_for_professional_pack"] and not asset["present"]
        ],
        "recommended_sets": resolved_sets,
        "security": {
            "raw_provider_payloads_excluded": True,
            "api_keys_excluded": True,
            "request_headers_excluded": True,
            "raw_result_rows_excluded": True,
        },
    }


def _publication_signature_summary(run_dir: Path, integrity, archive_paths: list[str]) -> dict[str, object]:
    if SIGNATURE_FILENAME not in archive_paths:
        return {
            "signature_key_id": None,
            "signature_algorithm": None,
            "signed_artifact_count": 0,
            "signature_manifest_matches_integrity": None,
            "unsigned_publication_artifacts": [
                artifact for artifact in archive_paths if artifact not in {INTEGRITY_FILENAME, SIGNATURE_FILENAME}
            ],
        }
    signature = load_signature_manifest(run_dir)
    signed_artifacts = dict(sorted(signature.signed_artifacts.items()))
    integrity_artifacts = dict(sorted(integrity.artifacts.items()))
    if signature.run_id != integrity.run_id or signed_artifacts != integrity_artifacts:
        raise ConfigError("signature manifest does not match integrity manifest; re-run `agentblaster sign`")
    unsigned_publication_artifacts = [
        artifact
        for artifact in archive_paths
        if artifact not in {INTEGRITY_FILENAME, SIGNATURE_FILENAME} and artifact not in signed_artifacts
    ]
    return {
        "signature_key_id": signature.key_id,
        "signature_algorithm": "hmac-sha256",
        "signed_artifact_count": len(signed_artifacts),
        "signature_manifest_matches_integrity": True,
        "unsigned_publication_artifacts": unsigned_publication_artifacts,
    }
