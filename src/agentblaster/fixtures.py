from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentblaster.models import (
    ApiContract,
    BenchmarkResult,
    ModelMetadata,
    ProviderRunMetadata,
    RawTraceMode,
    RetentionPolicy,
    RunManifest,
    SuiteDefinition,
    SuiteProvenance,
)

DASHBOARD_FIXTURE_PROFILE = "deterministic-redacted"
DASHBOARD_FIXTURE_RUN_IDS = ("run_dashboard_fixture_pass", "run_dashboard_fixture_fail")


@dataclass(frozen=True)
class DashboardFixture:
    profile: str
    runs_dir: Path
    manifest_path: Path
    run_ids: tuple[str, ...]
    artifact_paths: tuple[Path, ...]


def write_dashboard_fixture(
    output_dir: Path,
    *,
    profile: str = DASHBOARD_FIXTURE_PROFILE,
    overwrite: bool = False,
) -> DashboardFixture:
    """Write deterministic, redaction-safe dashboard runs for GUI selftests."""
    if profile != DASHBOARD_FIXTURE_PROFILE:
        raise ValueError(f"unknown dashboard fixture profile: {profile}")
    output_dir = output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    _prepare_output_dir(output_dir, overwrite=overwrite)

    artifact_paths: list[Path] = []
    artifact_paths.extend(_write_fixture_run(output_dir, run_id="run_dashboard_fixture_pass", ok=True))
    artifact_paths.extend(_write_fixture_run(output_dir, run_id="run_dashboard_fixture_fail", ok=False))
    manifest_path = output_dir / "dashboard-fixture.json"
    manifest = {
        "schema_version": "agentblaster.dashboard-fixture.v1",
        "profile": profile,
        "runs_dir": str(output_dir),
        "run_ids": list(DASHBOARD_FIXTURE_RUN_IDS),
        "contains_real_secrets": False,
        "contains_remote_calls": False,
        "raw_trace_mode": "redacted",
        "intended_for": ["dashboard gui tests", "Chrome/Codex validation", "Playwright fixtures"],
        "safety_notes": [
            "Fixture artifacts use mock local provider metadata only.",
            "No API keys or Authorization header values are stored.",
            "Raw response examples contain only redacted placeholders.",
        ],
        "artifact_count": len(artifact_paths),
        "artifact_sha256": {
            path.relative_to(output_dir).as_posix(): _sha256_file(path)
            for path in sorted(artifact_paths)
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "
", encoding="utf-8")
    artifact_paths.append(manifest_path)
    return DashboardFixture(
        profile=profile,
        runs_dir=output_dir,
        manifest_path=manifest_path,
        run_ids=DASHBOARD_FIXTURE_RUN_IDS,
        artifact_paths=tuple(artifact_paths),
    )


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    existing_fixture_paths = [output_dir / run_id for run_id in DASHBOARD_FIXTURE_RUN_IDS]
    existing_manifest = output_dir / "dashboard-fixture.json"
    existing_known = [path for path in [*existing_fixture_paths, existing_manifest] if path.exists()]
    unknown_entries = [path for path in output_dir.iterdir() if path.name not in {*DASHBOARD_FIXTURE_RUN_IDS, "dashboard-fixture.json"}]
    if unknown_entries:
        names = ", ".join(sorted(path.name for path in unknown_entries[:5]))
        raise ValueError(f"dashboard fixture output directory contains non-fixture entries: {names}")
    if existing_known and not overwrite:
        raise ValueError("dashboard fixture output already exists; pass --overwrite to replace known fixture artifacts")
    if overwrite:
        for path in existing_fixture_paths:
            if path.exists():
                shutil.rmtree(path)
        if existing_manifest.exists():
            existing_manifest.unlink()


def _write_fixture_run(output_dir: Path, *, run_id: str, ok: bool) -> list[Path]:
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    suite = _fixture_suite()
    manifest = _fixture_manifest(run_id=run_id, suite=suite, ok=ok)
    result = _fixture_result(run_id=run_id, ok=ok)

    written: list[Path] = []
    written.append(_write_json(run_dir / "manifest.json", manifest.model_dump(mode="json")))
    written.append(_write_json(run_dir / "suite.json", suite.model_dump(mode="json")))
    written.append(_write_jsonl(run_dir / "results.jsonl", [result.model_dump(mode="json")]))
    written.append(_write_json(run_dir / "summary.json", _summary_payload(run_id=run_id, ok=ok)))
    written.extend(_write_report_artifacts(run_dir, run_id=run_id, ok=ok))
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    written.append(
        _write_json(
            raw_dir / "fixture-case.response.json",
            {
                "fixture": True,
                "headers": {"Authorization": "Bearer [REDACTED]"},
                "body": {"message": result.message, "api_key": "[REDACTED]"},
            },
        )
    )
    written.append(_write_json(run_dir / "integrity.json", _integrity_payload(run_dir, written)))
    return written


def _fixture_manifest(*, run_id: str, suite: SuiteDefinition, ok: bool) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        suite=suite.name,
        provider="mock-local-dashboard",
        contract=ApiContract.OPENAI,
        model="fixture-qwen3.6-27b-dense",
        raw_trace_mode=RawTraceMode.REDACTED,
        created_at="2026-05-31T00:00:00Z" if ok else "2026-05-31T00:01:00Z",
        case_count=1,
        concurrency=1,
        suite_sha256=_sha256_json(suite.model_dump(mode="json")),
        case_sha256={case.id: _sha256_json(case.model_dump(mode="json")) for case in suite.cases},
        suite_snapshot_path="suite.json",
        suite_provenance=suite.provenance,
        metrics_artifacts=["metrics/prometheus-summary.json"],
        provider_metadata=ProviderRunMetadata(
            base_url="http://127.0.0.1:9999/v1",
            base_url_host="127.0.0.1",
            remote=False,
            native_adapter=None,
            adapter_name="mock-dashboard-fixture",
            adapter_version="agentblaster-fixture-v1",
            capabilities={"streaming": True, "tool_calling": True, "structured_output": True},
            metrics_url_host=None,
            tls_verify=True,
            ca_bundle=None,
        ),
        model_metadata=ModelMetadata(
            revision="fixture-revision",
            architecture="qwen3.6-dense",
            quantization="mock-f16",
            context_length=32768,
        ),
        retention_policy=RetentionPolicy(
            classification="internal",
            retain_days=7,
            raw_trace_retain_days=1,
            notes=["Generated dashboard GUI fixture; safe for local selftests."],
        ),
    )


def _fixture_suite() -> SuiteDefinition:
    return SuiteDefinition(
        name="dashboard-fixture",
        description="Deterministic redacted dashboard GUI fixture suite.",
        provenance=SuiteProvenance(
            origin="internal_regression",
            primary_source="AgentBlaster",
            license="MIT",
            risk_labels=["fixture", "redacted", "gui-selftest"],
            notes=["Generated by agentblaster fixtures for dashboard validation."],
        ),
        cases=[
            {
                "id": "fixture-case",
                "title": "Dashboard fixture case",
                "prompt": "Reply with exactly: agentblaster-fixture-ok",
                "expected_substring": "agentblaster-fixture-ok",
                "metrics": ["latency_ms", "ttft_ms", "tokens_per_second_decode"],
                "tags": ["fixture", "dashboard", "gui"],
                "risk_level": "low",
                "provenance": "AgentBlaster deterministic fixture",
                "license": "MIT",
            }
        ],
    )


def _fixture_result(*, run_id: str, ok: bool) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=run_id,
        case_id="fixture-case",
        case_title="Dashboard fixture case",
        scenario="dashboard-gui-fixture",
        case_tags=["fixture", "dashboard", "gui"],
        case_provenance="AgentBlaster deterministic fixture",
        case_risk_level="low",
        case_license="MIT",
        suite="dashboard-fixture",
        provider="mock-local-dashboard",
        contract=ApiContract.OPENAI,
        model="fixture-qwen3.6-27b-dense",
        ok=ok,
        provider_endpoint_host="127.0.0.1",
        provider_remote=False,
        adapter_name="mock-dashboard-fixture",
        adapter_version="agentblaster-fixture-v1",
        status_code=200 if ok else 200,
        request_started_at="2026-05-31T00:00:00Z",
        request_completed_at="2026-05-31T00:00:02Z" if ok else "2026-05-31T00:00:03Z",
        queue_ms=0.0,
        rate_limit_wait_ms=0.0,
        latency_ms=120.0 if ok else 180.0,
        input_tokens=128,
        output_tokens=12 if ok else 8,
        total_tokens=140 if ok else 136,
        cached_input_tokens=64,
        cache_write_tokens=64,
        cache_hit_ratio=0.5,
        total_cost_usd=0.0,
        ttft_ms=45.0 if ok else 60.0,
        prompt_eval_ms=30.0,
        decode_ms=70.0 if ok else 100.0,
        tokens_per_second_prefill=4266.667,
        tokens_per_second_decode=171.429 if ok else 80.0,
        raw_usage={"prompt_tokens": 128, "completion_tokens": 12 if ok else 8, "total_tokens": 140 if ok else 136},
        raw_stats={"fixture": True, "redacted": True},
        tool_calls_requested=0,
        tool_calls_emitted=0,
        tool_calls_valid=0,
        structured_output_valid=True,
        finish_reason="stop",
        failure_class=None if ok else "model_quality",
        message="agentblaster-fixture-ok" if ok else "fixture failure: expected marker missing",
        raw_response_path="raw/fixture-case.response.json",
    )


def _summary_payload(*, run_id: str, ok: bool) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "total_cases": 1,
        "passed": 1 if ok else 0,
        "failed": 0 if ok else 1,
        "duration_ms": 2000.0 if ok else 3000.0,
        "requests_per_second": 0.5 if ok else 0.333,
        "fixture": True,
        "redacted": True,
    }


def _write_report_artifacts(run_dir: Path, *, run_id: str, ok: bool) -> list[Path]:
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(exist_ok=True)
    status = "pass" if ok else "fail"
    paths = [
        _write_text(
            run_dir / "report.html",
            f"""<!doctype html><html><body><h1>AgentBlaster fixture report</h1><p>run: {run_id}</p><p>status: {status}</p><p>redacted: true</p></body></html>
""",
        ),
        _write_text(run_dir / "report.md", f"# AgentBlaster fixture report

- run: `{run_id}`
- status: `{status}`
- redacted: true
"),
        _write_json(run_dir / "publication.json", {"run_id": run_id, "status": status, "redacted": True, "fixture": True}),
        _write_text(
            run_dir / "report-card.svg",
            f"<svg xmlns="http://www.w3.org/2000/svg" width="640" height="320"><text x="32" y="80">AgentBlaster {status} fixture</text><text x="32" y="130">{run_id}</text></svg>
",
        ),
        _write_json(
            metrics_dir / "prometheus-summary.json",
            {"format": "agentblaster-prometheus-summary-v1", "fixture": True, "redacted": True, "run_id": run_id},
        ),
    ]
    return paths


def _integrity_payload(run_dir: Path, written: list[Path]) -> dict[str, Any]:
    return {
        "schema_version": "agentblaster.fixture-integrity.v1",
        "artifact_sha256": {
            path.relative_to(run_dir).as_posix(): _sha256_file(path)
            for path in sorted(written)
            if path.exists()
        },
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "
", encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "
" for row in rows), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
