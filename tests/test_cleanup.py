from __future__ import annotations

from datetime import UTC, datetime

from agentblaster.cleanup import apply_expired_cleanup, cleanup_run, plan_expired_cleanup
from agentblaster.models import ApiContract, RawTraceMode, RetentionPolicy, RunManifest


def test_cleanup_run_removes_selected_artifacts(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    raw_dir = run_dir / "raw"
    exports_dir = run_dir / "exports"
    raw_dir.mkdir(parents=True)
    exports_dir.mkdir()
    (raw_dir / "response.json").write_text("{}", encoding="utf-8")
    (exports_dir / "results.csv").write_text("x", encoding="utf-8")
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_dir / "report.md").write_text("# report", encoding="utf-8")
    (run_dir / "report-card.svg").write_text("<svg></svg>", encoding="utf-8")
    (run_dir / "publication.json").write_text("{}", encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "results.jsonl").write_text("{}", encoding="utf-8")

    removed = cleanup_run(run_dir, raw=True, reports=True, exports=True)

    assert raw_dir in removed
    assert exports_dir in removed
    assert run_dir / "report.html" in removed
    assert run_dir / "report.md" in removed
    assert run_dir / "report-card.svg" in removed
    assert run_dir / "publication.json" in removed
    assert not raw_dir.exists()
    assert not exports_dir.exists()
    assert not (run_dir / "report.html").exists()
    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "report-card.svg").exists()
    assert not (run_dir / "publication.json").exists()
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
