from pathlib import Path

from probe import report


def test_save_uses_incrementing_name_instead_of_overwriting(tmp_path: Path) -> None:
    target = tmp_path / "analysis.json"

    first = report.save({"value": 1}, target)
    second = report.save({"value": 2}, target)
    third = report.save({"value": 3}, target)

    assert first.name == "analysis.json"
    assert second.name == "analysis (1).json"
    assert third.name == "analysis (2).json"
    assert '"value": 1' in first.read_text(encoding="utf-8")
