"""Persistent user settings for the local WebUI."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "scoreBands": {
        "thresholds": [20, 50, 80, 90],
        "colors": ["#ffffff", "#8ec5ff", "#ffe07a", "#ffad66", "#ff78c8"],
    },
    "historyLimit": 0,
    "recursiveFolders": True,
    "historyCardSize": 250,
    "variableHistoryCards": True,
    "paths": {
        "music": str(ROOT),
        "reports": str(ROOT / "reports"),
        "models": str(ROOT / "models"),
    },
    "waveformPeaks": 180,
}


def _as_int(value: Any, fallback: int) -> int:
    """Coerce a persisted setting to int, keeping `fallback` for unusable values.

    A single malformed field must not discard the rest of the user's settings.
    """
    if isinstance(value, bool):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in {"true", "1", "yes", "on"}:
            return True
        if token in {"false", "0", "no", "off"}:
            return False
    return fallback


def _merged(data: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return result
    score_bands = data.get("scoreBands")
    if isinstance(score_bands, dict):
        thresholds = score_bands.get("thresholds")
        colors = score_bands.get("colors")
        if isinstance(thresholds, list) and len(thresholds) == 4:
            try:
                values = [int(value) for value in thresholds]
            except (TypeError, ValueError):
                values = []
            if len(values) == 4 and 0 < values[0] < values[1] < values[2] < values[3] < 100:
                result["scoreBands"]["thresholds"] = values
        if isinstance(colors, list) and len(colors) == 5:
            result["scoreBands"]["colors"] = [str(value) for value in colors]
    limit = _as_int(data.get("historyLimit"), result["historyLimit"])
    result["historyLimit"] = max(0, min(100000, limit))
    result["recursiveFolders"] = _as_bool(data.get("recursiveFolders"), result["recursiveFolders"])
    card_size = _as_int(data.get("historyCardSize"), result["historyCardSize"])
    result["historyCardSize"] = max(200, min(360, card_size))
    result["variableHistoryCards"] = _as_bool(data.get("variableHistoryCards"), result["variableHistoryCards"])
    peaks = _as_int(data.get("waveformPeaks"), result["waveformPeaks"])
    result["waveformPeaks"] = peaks if peaks in {120, 180, 300} else 180
    paths = data.get("paths")
    if isinstance(paths, dict):
        for key in ("music", "reports", "models"):
            raw = paths.get(key)
            if isinstance(raw, str) and raw.strip():
                try:
                    result["paths"][key] = str(Path(raw).expanduser().resolve())
                except (OSError, RuntimeError, ValueError):
                    continue
    return result


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return deepcopy(DEFAULT_SETTINGS)
    try:
        return _merged(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return deepcopy(DEFAULT_SETTINGS)


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    settings = _merged(data)
    for key in ("music", "reports", "models"):
        path = Path(settings["paths"][key])
        if not path.is_dir():
            raise ValueError(f"{key} 폴더를 찾을 수 없습니다: {path}")
    temporary = SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SETTINGS_PATH)
    return settings


def configured_path(name: str) -> Path:
    return Path(load_settings()["paths"][name])
