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


def test_repeated_identical_results_have_independent_favorites(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 0})
    payload = {
        "generatedAt": "2026-09-27T00:00:00+00:00",
        "results": [{"name": "same.wav", "file": "same.wav", "status": "completed", "totalScore": 50}],
    }

    history.save_history(json.loads(json.dumps(payload)))
    history.save_history(json.loads(json.dumps(payload)))
    items = history.load_history()

    assert len(items) == 2
    assert {item["name"] for item in items} == {"same.wav", "same (1).wav"}
    assert {item["sourceName"] for item in items} == {"same.wav"}
    assert items[0]["historyItemId"] != items[1]["historyItemId"]
    assert history.set_favorite(items[0]["id"], True) is True
    refreshed = history.load_history()
    assert sum(bool(item["favorite"]) for item in refreshed) == 1


def test_change_signature_changes_without_loading_payloads(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)

    before = history.change_signature()
    (history_dir / "run.json").write_text("{}", encoding="utf-8")
    after = history.change_signature()

    assert before["signature"] != after["signature"]
    assert after["fileCount"] == 1


def test_repeated_history_names_increment_without_changing_source_path(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 0})
    source_path = str(tmp_path / "song.flac")

    for _ in range(3):
        history.save_history({"results": [{"name": "song.flac", "file": source_path}]})

    items = history.load_history()
    assert {item["name"] for item in items} == {"song.flac", "song (1).flac", "song (2).flac"}
    assert {item["file"] for item in items} == {source_path}


def test_legacy_repeated_names_receive_display_suffix(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 0})
    for index in range(2):
        (history_dir / f"legacy-{index}.json").write_text(
            json.dumps({
                "generatedAt": f"2026-09-2{index + 1}T00:00:00+00:00",
                "results": [{"name": "legacy.wav", "file": "legacy.wav"}],
            }),
            encoding="utf-8",
        )

    items = history.load_history()

    assert [item["name"] for item in items] == ["legacy (1).wav", "legacy.wav"]


def test_report_and_history_copies_of_same_run_are_shown_once(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 0})
    payload = {
        "generatedAt": "2026-09-27T03:00:00+09:00",
        "results": [{"name": "same.wav", "file": "same.wav", "status": "completed", "totalScore": 42}],
    }
    (tmp_path / "saved-report.json").write_text(json.dumps(payload), encoding="utf-8")
    history.save_history(json.loads(json.dumps(payload)))

    items = history.load_history()

    assert len(items) == 1
    assert items[0].get("historyItemId")
