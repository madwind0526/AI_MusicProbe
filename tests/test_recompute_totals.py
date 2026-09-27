import json

import pytest

from scripts import recompute_totals


def test_recompute_preserves_saved_weights_and_updates_method(tmp_path) -> None:
    target = tmp_path / "history.json"
    target.write_text(json.dumps({
        "results": [{
            "status": "completed",
            "detectors": [
                {"name": "sonics", "score": 0.9},
                {"name": "lofcz", "score": 0.5},
            ],
            "detectorSettings": {
                "ensemble": {"method": "median", "weights": {"sonics": 2, "lofcz": 1}},
            },
        }],
    }), encoding="utf-8")

    assert recompute_totals._process_wrapped(target, "weightedGeometric") == 1
    saved = json.loads(target.read_text(encoding="utf-8"))["results"][0]

    assert saved["detectorSettings"]["ensemble"] == {
        "method": "weightedGeometric",
        "weights": {"sonics": 2, "lofcz": 1},
    }
    assert saved["scoreInfo"]["components"]["weights"] == {"sonics": 2.0, "lofcz": 1.0}
    assert not target.with_suffix(".json.tmp").exists()


def test_backup_preserves_the_original_before_rewriting(tmp_path) -> None:
    target = tmp_path / "history.json"
    original = {"results": [{
        "status": "completed",
        "detectors": [{"name": "sonics", "score": 0.9}, {"name": "lofcz", "score": 0.1}],
        "totalScore": 12.3,
        "confidence": 4.5,
    }]}
    target.write_text(json.dumps(original), encoding="utf-8")

    assert recompute_totals._process_wrapped(target, "robustMean", dry_run=False, backup=True) == 1

    backup = target.with_suffix(".json.bak")
    assert backup.is_file()
    # The backup is byte-identical to what was on disk before the rewrite.
    assert json.loads(backup.read_text(encoding="utf-8")) == original
    # ...and the live file really did change.
    assert json.loads(target.read_text(encoding="utf-8")) != original


def test_backup_does_not_clobber_an_earlier_backup(tmp_path) -> None:
    target = tmp_path / "history.json"
    original = {"results": [{
        "status": "completed",
        "detectors": [{"name": "sonics", "score": 0.9}, {"name": "lofcz", "score": 0.1}],
        "totalScore": 12.3,
    }]}
    target.write_text(json.dumps(original), encoding="utf-8")

    recompute_totals._process_wrapped(target, "robustMean", dry_run=False, backup=True)
    # A second run must not replace the pristine original with the already-recomputed file.
    recompute_totals._process_wrapped(target, "robustMean", dry_run=False, backup=True)

    backup = target.with_suffix(".json.bak")
    assert json.loads(backup.read_text(encoding="utf-8")) == original


def test_backup_failure_aborts_before_rewriting(tmp_path, monkeypatch) -> None:
    target = tmp_path / "history.json"
    original = {"results": [{
        "status": "completed",
        "detectors": [{"name": "sonics", "score": 0.9}],
        "totalScore": 1.0,
    }]}
    target.write_text(json.dumps(original), encoding="utf-8")

    def fail_copy(*_args, **_kwargs):
        raise OSError("backup unavailable")

    monkeypatch.setattr(recompute_totals.shutil, "copy2", fail_copy)

    with pytest.raises(OSError, match="backup unavailable"):
        recompute_totals._process_wrapped(target, "robustMean", backup=True)
    assert json.loads(target.read_text(encoding="utf-8")) == original


def test_dry_run_never_writes_a_backup(tmp_path) -> None:
    target = tmp_path / "history.json"
    target.write_text(json.dumps({"results": [{
        "status": "completed",
        "detectors": [{"name": "sonics", "score": 0.9}, {"name": "lofcz", "score": 0.1}],
        "totalScore": 12.3,
    }]}), encoding="utf-8")

    assert recompute_totals._process_wrapped(target, "robustMean", dry_run=True, backup=True) == 1
    assert not target.with_suffix(".json.bak").exists()


def test_unchanged_results_create_no_backup(tmp_path) -> None:
    target = tmp_path / "history.json"
    payload = {"results": [{
        "status": "completed",
        "detectors": [{"name": "sonics", "score": 0.5}],
        "totalScore": 50.0,
    }]}
    target.write_text(json.dumps(payload), encoding="utf-8")
    # Align the file with the current scoring first, then confirm a no-op run
    # does not litter the reports directory with .bak files.
    assert recompute_totals._process_wrapped(target, "robustMean", dry_run=False, backup=True) == 1
    assert recompute_totals._process_wrapped(target, "robustMean", dry_run=False, backup=True) == 0


def test_recompute_dry_run_does_not_write(tmp_path) -> None:
    target = tmp_path / "history.json"
    original = {"results": [{
        "status": "completed",
        "detectors": [{"name": "sonics", "score": 0.9}],
        "totalScore": 0,
    }]}
    target.write_text(json.dumps(original), encoding="utf-8")

    assert recompute_totals._process_wrapped(target, "robustMean", dry_run=True) == 1
    assert json.loads(target.read_text(encoding="utf-8")) == original
