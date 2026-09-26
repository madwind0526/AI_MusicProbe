"""Persistent analysis history used by the WebUI."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .app_settings import load_settings
from .config import REPORTS_DIR

HISTORY_DIR = REPORTS_DIR / "history"
_SAVE_LOCK = threading.Lock()


def _favorites_path() -> Path:
    return HISTORY_DIR / "favorites.json"


def _item_key(item: dict) -> str:
    history_item_id = item.get("historyItemId")
    if history_item_id:
        return f"id:{history_item_id}"
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


def _name_with_index(name: str, index: int) -> str:
    if index <= 0:
        return name
    path = Path(name)
    return f"{path.stem} ({index}){path.suffix}"


def _saved_name_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not HISTORY_DIR.is_dir():
        return counts
    for source in HISTORY_DIR.glob("*.json"):
        if source == _favorites_path():
            continue
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            original = str(result.get("sourceName") or result.get("name") or "")
            if original:
                key = original.casefold()
                counts[key] = counts.get(key, 0) + 1
    return counts


def save_history(payload: dict) -> Path:
    with _SAVE_LOCK:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        name_counts = _saved_name_counts()
        for result in payload.get("results", []):
            if isinstance(result, dict):
                result.setdefault("historyItemId", uuid4().hex)
                original = str(result.get("sourceName") or result.get("name") or Path(str(result.get("file") or "음원")).name)
                result["sourceName"] = original
                key = original.casefold()
                index = name_counts.get(key, 0)
                result["name"] = _name_with_index(original, index)
                name_counts[key] = index + 1
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = HISTORY_DIR / f"{stamp}-{uuid4().hex[:8]}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        trim_history(load_settings()["historyLimit"])
        return target


def change_signature() -> dict:
    """Return a cheap file-system token without parsing every history payload."""
    sources = []
    if REPORTS_DIR.is_dir():
        sources.extend(REPORTS_DIR.glob("*.json"))
    if HISTORY_DIR.is_dir():
        sources.extend(HISTORY_DIR.glob("*.json"))
    entries = []
    for source in sorted(set(sources), key=lambda path: str(path).casefold()):
        try:
            stat = source.stat()
        except OSError:
            continue
        entries.append(f"{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}")
    return {"fileCount": len(entries), "signature": "|".join(entries)}


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
            # The budget is shared across files on purpose: historyLimit caps the
            # total number of regular items kept, newest first, and a file whose
            # items all fall outside the budget is dropped. Favorites are exempt.
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
            item["_historyCopy"] = source.parent == HISTORY_DIR
            items.append(item)

    history_copy_keys = {
        (
            str(item.get("generatedAt", "")),
            str(item.get("file", "")).casefold(),
            str(item.get("totalScore")),
            str(item.get("status", "")),
        )
        for item in items
        if item.get("_historyCopy")
    }
    filtered_items = []
    for item in items:
        key = (
            str(item.get("generatedAt", "")),
            str(item.get("file", "")).casefold(),
            str(item.get("totalScore")),
            str(item.get("status", "")),
        )
        if not item.get("_historyCopy") and key in history_copy_keys:
            continue
        item.pop("_historyCopy", None)
        filtered_items.append(item)
    items = filtered_items

    favorites = _load_favorites()
    legacy_counts: dict[str, int] = {}
    for item in sorted(items, key=lambda entry: str(entry.get("generatedAt", ""))):
        original = str(item.get("sourceName") or item.get("name") or "")
        key = original.casefold()
        index = legacy_counts.get(key, 0)
        if "sourceName" not in item and index:
            item["name"] = _name_with_index(original, index)
        legacy_counts[key] = index + 1
    ordered = sorted(items, key=lambda item: str(item.get("generatedAt", "")), reverse=True)
    for item in ordered:
        item["favorite"] = _item_key(item) in favorites
    limit = load_settings()["historyLimit"]
    if limit <= 0:
        return ordered
    favorite_items = [item for item in ordered if item["favorite"]]
    regular_items = [item for item in ordered if not item["favorite"]][:limit]
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
