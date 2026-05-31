from __future__ import annotations

from agentblaster.cleanup import cleanup_run


def test_cleanup_run_removes_selected_artifacts(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    raw_dir = run_dir / "raw"
    exports_dir = run_dir / "exports"
    raw_dir.mkdir(parents=True)
    exports_dir.mkdir()
    (raw_dir / "response.json").write_text("{}", encoding="utf-8")
    (exports_dir / "results.csv").write_text("x", encoding="utf-8")
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "results.jsonl").write_text("{}", encoding="utf-8")

    removed = cleanup_run(run_dir, raw=True, reports=True, exports=True)

    assert raw_dir in removed
    assert exports_dir in removed
    assert run_dir / "report.html" in removed
    assert not raw_dir.exists()
    assert not exports_dir.exists()
    assert not (run_dir / "report.html").exists()
    assert (run_dir / "results.jsonl").exists()


def test_cleanup_run_can_remove_entire_run_dir(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()

    removed = cleanup_run(run_dir, all_artifacts=True)

    assert removed == [run_dir]
    assert not run_dir.exists()
