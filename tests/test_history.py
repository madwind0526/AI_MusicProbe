import json
from pathlib import Path

from probe import history


def test_history_load_and_delete_one_result(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    source = history_dir / "run.json"
    source.write_text(
        json.dumps({
            "generatedAt": "2026-09-26T12:00:00+00:00",
            "results": [
                {"name": "a.wav", "file": str(tmp_path / "a.wav")},
                {"name": "b.wav", "file": str(tmp_path / "b.wav")},
            ],
        }),
        encoding="utf-8",
    )

    items = history.load_history()
    assert [item["id"] for item in items] == ["run:0", "run:1"]
    assert history.delete_history("run:0") is True
    assert [item["name"] for item in history.load_history()] == ["b.wav"]


def test_history_limit_keeps_favorite_and_newest_regular(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    settings = {"historyLimit": 0}
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: settings)

    for index, name in enumerate(("old.wav", "middle.wav", "new.wav"), start=1):
        (history_dir / f"{index}.json").write_text(
            json.dumps({
                "generatedAt": f"2026-09-2{index}T12:00:00+00:00",
                "results": [{"name": name, "file": str(tmp_path / name), "status": "completed", "totalScore": index}],
            }),
            encoding="utf-8",
        )

    assert history.set_favorite("1:0", True) is True
    settings["historyLimit"] = 1
    history.trim_history(1)

    items = history.load_history()
    assert [item["name"] for item in items] == ["new.wav", "old.wav"]
    assert next(item for item in items if item["name"] == "old.wav")["favorite"] is True
    assert not (history_dir / "2.json").exists()
