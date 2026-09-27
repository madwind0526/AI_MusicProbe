from pathlib import Path

from probe import report
from probe.stages import StageSet


def test_save_uses_incrementing_name_instead_of_overwriting(tmp_path: Path) -> None:
    target = tmp_path / "analysis.json"

    first = report.save({"value": 1}, target)
    second = report.save({"value": 2}, target)
    third = report.save({"value": 3}, target)

    assert first.name == "analysis.json"
    assert second.name == "analysis (1).json"
    assert third.name == "analysis (2).json"
    assert '"value": 1' in first.read_text(encoding="utf-8")


def test_delta_requires_the_actual_first_and_last_stage(monkeypatch, tmp_path: Path) -> None:
    first = tmp_path / "first.wav"
    middle = tmp_path / "middle.wav"
    last = tmp_path / "last.wav"
    stage_set = StageSet("chain", {"source": first, "master": middle, "final": last})
    profiles = {
        first: {"shared": 1.0},
        middle: {"shared": 2.0, "middle_only": 10.0},
        last: {"shared": 4.0, "middle_only": 20.0},
    }
    monkeypatch.setattr(report, "_profile", lambda path: profiles[path])
    monkeypatch.setattr(report, "_flags", lambda *_args: [])
    monkeypatch.setattr(report, "_peak_diff", lambda *_args: [])

    result = report.analyze(stage_set)

    assert result["target"]["deltas"]["shared"]["change"] == 3.0
    assert "middle_only" not in result["target"]["deltas"]
