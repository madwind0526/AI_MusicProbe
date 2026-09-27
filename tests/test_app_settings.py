import json
from pathlib import Path

from probe import app_settings


def _write(tmp_path: Path, monkeypatch, data: dict) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(app_settings, "SETTINGS_PATH", path)
    return path


def test_one_corrupt_field_keeps_every_other_saved_setting(tmp_path: Path, monkeypatch) -> None:
    saved = {
        "historyLimit": 25,
        "historyCardSize": 320,
        "waveformPeaks": 300,
        "recursiveFolders": False,
        "paths": {"music": str(tmp_path), "reports": str(tmp_path), "models": str(tmp_path)},
        "scoreBands": {"thresholds": [10, 40, 70, 95], "colors": ["#1", "#2", "#3", "#4", "#5"]},
    }
    saved["historyLimit"] = "not-a-number"
    _write(tmp_path, monkeypatch, saved)

    settings = app_settings.load_settings()

    # The broken field falls back to its default...
    assert settings["historyLimit"] == app_settings.DEFAULT_SETTINGS["historyLimit"]
    # ...but everything else survives. Before the fix the whole file was discarded.
    assert settings["historyCardSize"] == 320
    assert settings["waveformPeaks"] == 300
    assert settings["recursiveFolders"] is False
    assert settings["scoreBands"]["thresholds"] == [10, 40, 70, 95]
    assert settings["scoreBands"]["colors"] == ["#1", "#2", "#3", "#4", "#5"]
    assert settings["paths"]["reports"] == str(tmp_path)


def test_corrupt_values_of_every_type_do_not_reset_settings(tmp_path: Path, monkeypatch) -> None:
    saved = {
        "historyLimit": None,
        "historyCardSize": [320],
        "waveformPeaks": {"a": 1},
        "recursiveFolders": "false",
        "variableHistoryCards": 0,
        "scoreBands": {"thresholds": ["x", None, [], {}], "colors": ["#1", "#2", "#3", "#4", "#5"]},
        "paths": {"music": str(tmp_path), "reports": 12345, "models": None},
    }
    _write(tmp_path, monkeypatch, saved)

    settings = app_settings.load_settings()

    assert settings["historyLimit"] == app_settings.DEFAULT_SETTINGS["historyLimit"]
    assert settings["historyCardSize"] == app_settings.DEFAULT_SETTINGS["historyCardSize"]
    assert settings["waveformPeaks"] == app_settings.DEFAULT_SETTINGS["waveformPeaks"]
    # Hand-edited string booleans are honoured instead of being truthy by accident.
    assert settings["recursiveFolders"] is False
    assert settings["variableHistoryCards"] is False
    assert settings["scoreBands"]["thresholds"] == app_settings.DEFAULT_SETTINGS["scoreBands"]["thresholds"]
    assert settings["scoreBands"]["colors"] == ["#1", "#2", "#3", "#4", "#5"]
    # A non-string path is ignored, so the default reports dir is kept.
    assert settings["paths"]["reports"] == app_settings.DEFAULT_SETTINGS["paths"]["reports"]
    assert settings["paths"]["music"] == str(tmp_path)


def test_malformed_json_still_falls_back_to_all_defaults(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(app_settings, "SETTINGS_PATH", path)

    assert app_settings.load_settings() == app_settings.DEFAULT_SETTINGS


def test_boolean_coercion_covers_common_spellings() -> None:
    for truthy in (True, 1, "true", "True", " yes ", "on", 3.5):
        assert app_settings._as_bool(truthy, False) is True
    for falsy in (False, 0, "false", "FALSE", " no ", "off", 0.0):
        assert app_settings._as_bool(falsy, True) is False
    # Unrecognised input keeps the caller's default in both directions.
    assert app_settings._as_bool("maybe", True) is True
    assert app_settings._as_bool("maybe", False) is False
    assert app_settings._as_bool(None, True) is True


def test_int_coercion_never_raises() -> None:
    assert app_settings._as_int("42", 7) == 42
    assert app_settings._as_int(42.9, 7) == 42
    assert app_settings._as_int("bad", 7) == 7
    assert app_settings._as_int(None, 7) == 7
    assert app_settings._as_int([1], 7) == 7
    # Booleans are not treated as 0/1, since that is never a deliberate setting.
    assert app_settings._as_int(True, 7) == 7
    assert app_settings._as_int(False, 7) == 7
