import json
from datetime import datetime, timezone
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


def test_non_object_favorites_and_history_files_are_ignored(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 0})
    (history_dir / "favorites.json").write_text("[]", encoding="utf-8")
    (history_dir / "invalid.json").write_text("[]", encoding="utf-8")

    saved = history.save_history({"results": [{"name": "safe.wav", "file": "safe.wav"}]})

    assert saved.is_file()
    assert [item["name"] for item in history.load_history()] == ["safe.wav"]


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


def test_delete_history_rejects_paths_outside_report_directories(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    outside = tmp_path.parent / "outside.json"
    outside.write_text(json.dumps({"results": [{"name": "keep.wav"}]}), encoding="utf-8")
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)

    assert history.delete_history("../outside:0") is False
    assert outside.is_file()


def test_mixed_utc_offsets_sort_chronologically_not_lexically(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 0})
    # 20:00+00:00 is 2 hours LATER than 03:00+09:00, but sorts lower as text.
    older = {"generatedAt": "2026-09-27T03:00:00+09:00", "results": [{"name": "older.wav", "file": "older.wav"}]}
    newer = {"generatedAt": "2026-09-26T20:00:00+00:00", "results": [{"name": "newer.wav", "file": "newer.wav"}]}
    history.save_history(json.loads(json.dumps(older)))
    history.save_history(json.loads(json.dumps(newer)))

    items = history.load_history()

    assert [item["name"] for item in items] == ["newer.wav", "older.wav"]


def test_zulu_and_offset_timestamps_are_compared_on_one_scale(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 0})
    zulu = {"generatedAt": "2026-09-26T20:00:00Z", "results": [{"name": "zulu.wav", "file": "zulu.wav"}]}
    offset = {"generatedAt": "2026-09-26T21:30:00+02:00", "results": [{"name": "offset.wav", "file": "offset.wav"}]}
    history.save_history(json.loads(json.dumps(zulu)))
    history.save_history(json.loads(json.dumps(offset)))

    items = history.load_history()

    # 20:00Z is 20:00 UTC, while 21:30+02:00 is 19:30 UTC, so Z sorts first.
    # Lexically "2026-09-26T21..." would have outranked "2026-09-26T20...".
    assert [item["name"] for item in items] == ["zulu.wav", "offset.wav"]


def test_trim_history_keeps_the_chronologically_newest_run(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 1})
    older = {"generatedAt": "2026-09-27T03:00:00+09:00", "results": [{"name": "older.wav", "file": "older.wav"}]}
    newer = {"generatedAt": "2026-09-26T20:00:00+00:00", "results": [{"name": "newer.wav", "file": "newer.wav"}]}
    history.save_history(json.loads(json.dumps(older)))
    history.save_history(json.loads(json.dumps(newer)))

    history.trim_history(1)

    assert [item["name"] for item in history.load_history()] == ["newer.wav"]


def test_favorites_and_regular_items_merge_in_chronological_order(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 5})
    # "fav" is the older run in real time but sorts later lexically.
    fav = {"generatedAt": "2026-09-27T03:00:00+09:00", "results": [{"name": "fav.wav", "file": "fav.wav"}]}
    regular = {"generatedAt": "2026-09-26T20:00:00+00:00", "results": [{"name": "regular.wav", "file": "regular.wav"}]}
    history.save_history(json.loads(json.dumps(fav)))
    history.save_history(json.loads(json.dumps(regular)))
    fav_id = next(item["id"] for item in history.load_history() if item["name"] == "fav.wav")
    assert history.set_favorite(fav_id, True) is True

    items = history.load_history()

    assert [item["name"] for item in items] == ["regular.wav", "fav.wav"]
    assert [item["favorite"] for item in items] == [False, True]


def test_trim_history_does_not_stat_a_report_that_has_a_timestamp(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 1})
    target = history_dir / "a.json"
    target.write_text(json.dumps({
        "generatedAt": "2026-09-27T10:00:00+00:00",
        "results": [{"name": "a.wav", "file": "a.wav"}, {"name": "b.wav", "file": "b.wav"}],
    }), encoding="utf-8")

    real_stat = Path.stat
    calls: list[str] = []

    def failing_stat(self: Path, *args, **kwargs):
        if self.name == "a.json":
            calls.append(self.name)
            raise OSError("simulated stat failure")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", failing_stat)
    history.trim_history(1)
    monkeypatch.undo()

    # The mtime fallback must stay lazy: a report that carries a timestamp is
    # processed without touching the filesystem, so a locked file is not skipped.
    assert calls == []
    assert [item["name"] for item in json.loads(target.read_text(encoding="utf-8"))["results"]] == ["a.wav"]


def test_trim_history_falls_back_to_mtime_when_the_timestamp_is_missing(tmp_path: Path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    monkeypatch.setattr(history, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "load_settings", lambda: {"historyLimit": 1})
    target = history_dir / "b.json"
    target.write_text(json.dumps({
        "results": [{"name": "a.wav", "file": "a.wav"}, {"name": "b.wav", "file": "b.wav"}],
    }), encoding="utf-8")

    history.trim_history(1)

    # Without a timestamp the mtime fallback orders the report, so it is still trimmed.
    assert [item["name"] for item in json.loads(target.read_text(encoding="utf-8"))["results"]] == ["a.wav"]


def test_sort_timestamp_handles_malformed_and_missing_values() -> None:
    floor = history._sort_timestamp("")
    assert floor == history._sort_timestamp(None)
    assert history._sort_timestamp("not-a-date") == floor
    # An unparseable value still falls back to mtime rather than dropping to the floor.
    assert history._sort_timestamp("not-a-date", fallback_mtime=0.0) == datetime.fromtimestamp(0.0, tz=timezone.utc)
    # Numeric mtime-style values are accepted directly.
    assert history._sort_timestamp(0.0) == datetime.fromtimestamp(0.0, tz=timezone.utc)
    # Naive timestamps are treated as UTC rather than local time.
    assert history._sort_timestamp("2026-09-26T20:00:00") == history._sort_timestamp("2026-09-26T20:00:00+00:00")
    # Out-of-range values must not raise.
    assert history._sort_timestamp(1e30) == datetime.min.replace(tzinfo=timezone.utc)
