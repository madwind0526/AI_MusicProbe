"""Persistent analysis history used by the WebUI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .app_settings import load_settings
from .config import REPORTS_DIR

HISTORY_DIR = REPORTS_DIR / "history"


def _favorites_path() -> Path:
    return HISTORY_DIR / "favorites.json"


def _item_key(item: dict) -> str:
    return "|".join((str(item.get("file", "")).casefold(), str(item.get("totalScore")), str(item.get("status", ""))))


def _load_favorites() -> set[str]:
    path = _favorites_path()
    if not path.is_file():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(value) for value in payload.get("items", [])}
    except (OSError, json.JSONDecodeError):
        return set()


def _save_favorites(items: set[str]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    target = _favorites_path()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"items": sorted(items)}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def save_history(payload: dict) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = HISTORY_DIR / f"{stamp}-{uuid4().hex[:8]}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    trim_history(load_settings()["historyLimit"])
    return target


def trim_history(limit: int) -> None:
    if limit <= 0 or not HISTORY_DIR.is_dir():
        return
    remaining = limit
    favorites = _load_favorites()
    reports = []
    for source in HISTORY_DIR.glob("*.json"):
        if source == _favorites_path():
            continue
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            generated_at = str(payload.get("generatedAt") or source.stat().st_mtime)
            reports.append((generated_at, source, payload))
        except (OSError, json.JSONDecodeError):
            continue
    for _, source, payload in sorted(reports, key=lambda entry: entry[0], reverse=True):
        try:
            results = payload.get("results")
            if not isinstance(results, list):
                continue
            kept = []
            for result in results:
                if isinstance(result, dict) and _item_key(result) in favorites:
                    kept.append(result)
                elif remaining > 0:
                    kept.append(result)
                    remaining -= 1
            if not kept:
                source.unlink()
                continue
            if len(kept) != len(results):
                payload["results"] = kept
                source.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            continue


def load_history() -> list[dict]:
    sources = []
    if REPORTS_DIR.is_dir():
        sources.extend(REPORTS_DIR.glob("*.json"))
    if HISTORY_DIR.is_dir():
        sources.extend(HISTORY_DIR.glob("*.json"))

    items = []
    for source in sources:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results = payload.get("results")
        if not isinstance(results, list):
            continue
        generated_at = payload.get("generatedAt") or datetime.fromtimestamp(
            source.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds")
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            item = dict(result)
            item["id"] = f"{source.stem}:{index}"
            item["generatedAt"] = generated_at
            items.append(item)
    favorites = _load_favorites()
    ordered = sorted(items, key=lambda item: str(item.get("generatedAt", "")), reverse=True)
    unique = []
    seen = set()
    for item in ordered:
        key = (str(item.get("file", "")).casefold(), item.get("totalScore"), item.get("status"))
        if key in seen:
            continue
        seen.add(key)
        item["favorite"] = _item_key(item) in favorites
        unique.append(item)
    limit = load_settings()["historyLimit"]
    if limit <= 0:
        return unique
    favorite_items = [item for item in unique if item["favorite"]]
    regular_items = [item for item in unique if not item["favorite"]][:limit]
    return sorted(favorite_items + regular_items, key=lambda item: str(item.get("generatedAt", "")), reverse=True)


def set_favorite(item_id: str, favorite: bool) -> bool:
    item = next((entry for entry in load_history() if entry.get("id") == item_id), None)
    if item is None:
        return False
    favorites = _load_favorites()
    key = _item_key(item)
    if favorite:
        favorites.add(key)
    else:
        favorites.discard(key)
    _save_favorites(favorites)
    return True


def delete_history(item_id: str) -> bool:
    try:
        stem, raw_index = item_id.rsplit(":", 1)
        index = int(raw_index)
    except (ValueError, TypeError):
        return False
    candidates = [REPORTS_DIR / f"{stem}.json", HISTORY_DIR / f"{stem}.json"]
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        return False
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        results = payload.get("results")
        if not isinstance(results, list) or not 0 <= index < len(results):
            return False
        removed = results.pop(index)
        favorites = _load_favorites()
        favorites.discard(_item_key(removed))
        _save_favorites(favorites)
        if not results:
            source.unlink()
        else:
            source.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except (OSError, json.JSONDecodeError):
        return False
