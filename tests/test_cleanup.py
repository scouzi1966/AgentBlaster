from __future__ import annotations

from datetime import UTC, datetime

from agentblaster.cleanup import apply_expired_cleanup, cleanup_run, plan_cleanup_run, plan_expired_cleanup
from agentblaster.models import ApiContract, RawTraceMode, RetentionPolicy, RunManifest


def test_cleanup_run_removes_selected_artifacts(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    raw_dir = run_dir / "raw"
    exports_dir = run_dir / "exports"
    cache_dir = run_dir / "cache"
    temp_dir = run_dir / "tmp"
    bundle_dir = run_dir / "publication-bundles"
    bundle_zip = run_dir / "qwen.agentblaster-publication.zip"
    raw_dir.mkdir(parents=True)
    exports_dir.mkdir()
    cache_dir.mkdir()
    temp_dir.mkdir()
    bundle_dir.mkdir()
    (raw_dir / "response.json").write_text("{}", encoding="utf-8")
    (exports_dir / "results.csv").write_text("x", encoding="utf-8")
    (cache_dir / "prefill.bin").write_text("cache", encoding="utf-8")
    (temp_dir / "scratch.json").write_text("{}", encoding="utf-8")
    (bundle_dir / "bundle-manifest.json").write_text("{}", encoding="utf-8")
    bundle_zip.write_text("zip", encoding="utf-8")
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_dir / "report.md").write_text("# report", encoding="utf-8")
    (run_dir / "report.pdf").write_text("%PDF-1.4\n", encoding="utf-8")
    (run_dir / "report-card.svg").write_text("<svg></svg>", encoding="utf-8")
    (run_dir / "report-card.png").write_bytes(b"\x89PNG\n")
    (run_dir / "publication.json").write_text("{}", encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "results.jsonl").write_text("{}", encoding="utf-8")

    removed = cleanup_run(run_dir, raw=True, reports=True, exports=True, caches=True, temp=True, bundles=True)

    assert raw_dir in removed
    assert exports_dir in removed
    assert cache_dir in removed
    assert temp_dir in removed
    assert bundle_dir in removed
    assert bundle_zip in removed
    assert run_dir / "report.html" in removed
    assert run_dir / "report.md" in removed
    assert run_dir / "report.pdf" in removed
    assert run_dir / "report-card.svg" in removed
    assert run_dir / "report-card.png" in removed
    assert run_dir / "publication.json" in removed
    assert not raw_dir.exists()
    assert not exports_dir.exists()
    assert not cache_dir.exists()
    assert not temp_dir.exists()
    assert not bundle_dir.exists()
    assert not bundle_zip.exists()
    assert not (run_dir / "report.html").exists()
    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "report.pdf").exists()
    assert not (run_dir / "report-card.svg").exists()
    assert not (run_dir / "report-card.png").exists()
    assert not (run_dir / "publication.json").exists()
    assert (run_dir / "results.jsonl").exists()


def test_plan_cleanup_run_lists_selected_artifacts_without_deleting(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    raw_dir = run_dir / "raw"
    cache_dir = run_dir / "cache"
    bundle_zip = run_dir / "qwen.agentblaster-publication.zip"
    raw_dir.mkdir(parents=True)
    cache_dir.mkdir()
    (raw_dir / "response.json").write_text("{}", encoding="utf-8")
    (cache_dir / "prefill.bin").write_text("cache", encoding="utf-8")
    bundle_zip.write_text("zip", encoding="utf-8")
    (run_dir / "results.jsonl").write_text("{}", encoding="utf-8")

    planned = plan_cleanup_run(run_dir, raw=True, caches=True, bundles=True)

    assert raw_dir in planned
    assert cache_dir in planned
    assert bundle_zip in planned
    assert raw_dir.exists()
    assert cache_dir.exists()
    assert bundle_zip.exists()
    assert (run_dir / "results.jsonl").exists()


def test_cleanup_run_can_remove_entire_run_dir(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()

    removed = cleanup_run(run_dir, all_artifacts=True)

    assert removed == [run_dir]
    assert not run_dir.exists()


def test_plan_expired_cleanup_detects_raw_and_full_run_expiration(tmp_path) -> None:
    raw_run = _write_manifest_run(
        tmp_path,
        run_id="run_raw_expired",
        created_at="2026-05-01T00:00:00+00:00",
        retention_policy=RetentionPolicy(classification="confidential", retain_days=90, raw_trace_retain_days=7),
        raw=True,
    )
    full_run = _write_manifest_run(
        tmp_path,
        run_id="run_full_expired",
        created_at="2026-04-01T00:00:00+00:00",
        retention_policy=RetentionPolicy(classification="restricted", retain_days=30, raw_trace_retain_days=7),
        raw=True,
    )
    _write_manifest_run(
        tmp_path,
        run_id="run_current",
        created_at="2026-05-30T00:00:00+00:00",
        retention_policy=RetentionPolicy(classification="internal", retain_days=30, raw_trace_retain_days=7),
        raw=True,
    )

    actions = plan_expired_cleanup(tmp_path, now=datetime(2026, 5, 31, tzinfo=UTC))

    assert [(action.action, action.run_id) for action in actions] == [
        ("run", "run_full_expired"),
        ("raw", "run_raw_expired"),
    ]
    assert actions[0].classification == "restricted"
    assert actions[1].classification == "confidential"
    assert (raw_run / "raw").exists()
    assert full_run.exists()


def test_apply_expired_cleanup_removes_planned_artifacts(tmp_path) -> None:
    raw_run = _write_manifest_run(
        tmp_path,
        run_id="run_raw_expired",
        created_at="2026-05-01T00:00:00+00:00",
        retention_policy=RetentionPolicy(retain_days=90, raw_trace_retain_days=7),
        raw=True,
    )
    full_run = _write_manifest_run(
        tmp_path,
        run_id="run_full_expired",
        created_at="2026-04-01T00:00:00+00:00",
        retention_policy=RetentionPolicy(retain_days=30, raw_trace_retain_days=7),
        raw=True,
    )
    actions = plan_expired_cleanup(tmp_path, now=datetime(2026, 5, 31, tzinfo=UTC))

    applied = apply_expired_cleanup(actions)

    assert not full_run.exists()
    assert raw_run.exists()
    assert not (raw_run / "raw").exists()
    assert applied[0].removed
    assert applied[1].removed


def _write_manifest_run(
    tmp_path,
    *,
    run_id: str,
    created_at: str,
    retention_policy: RetentionPolicy,
    raw: bool,
):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    if raw:
        raw_dir = run_dir / "raw"
        raw_dir.mkdir()
        (raw_dir / "case.response.json").write_text("{}", encoding="utf-8")
    manifest = RunManifest(
        run_id=run_id,
        suite="smoke",
        provider="local",
        contract=ApiContract.OPENAI,
        model="qwen-test",
        raw_trace_mode=RawTraceMode.REDACTED,
        created_at=created_at,
        retention_policy=retention_policy,
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return run_dir
