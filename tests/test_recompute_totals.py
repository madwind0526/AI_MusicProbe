import json

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
