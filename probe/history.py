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
_SAVE_LOCK = threading.RLock()


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _favorites_path() -> Path:
    return HISTORY_DIR / "favorites.json"


def _item_key(item: dict) -> str:
    history_item_id = item.get("historyItemId")
    if history_item_id:
        return f"id:{history_item_id}"
    return "|".join((str(item.get("file", "")).casefold(), str(item.get("totalScore")), str(item.get("status", ""))))


def _sort_timestamp(value: object, fallback_mtime: float | None = None) -> datetime:
    """Normalise a report timestamp into an aware datetime for ordering.

    ISO-8601 text does not sort chronologically when UTC offsets differ, and
    mtime fallbacks are floats, so both forms are converted before comparing.
    Unparseable or absent values sort last, matching the empty-string behaviour.
    """
    epoch_floor = datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return epoch_floor
    if value:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    if fallback_mtime is None:
        return epoch_floor
    try:
        return datetime.fromtimestamp(fallback_mtime, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return epoch_floor


def _load_favorites() -> set[str]:
    path = _favorites_path()
    if not path.is_file():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return set()
        return {str(value) for value in payload.get("items", [])}
    except (OSError, json.JSONDecodeError):
        return set()


def _save_favorites(items: set[str]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(_favorites_path(), {"items": sorted(items)})


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
        if not isinstance(payload, dict):
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
        _atomic_write_json(target, payload)
        trim_history(load_settings()["historyLimit"])
        return target


def change_signature() -> dict:
    """Return a cheap file-system token without parsing every history payload.

    Scoped to HISTORY_DIR only, matching `load_history()`: a REPORTS_DIR-only
    change (e.g. a legacy stage-compare "저장") does not affect 분석 이력 anymore.
    """
    sources = list(HISTORY_DIR.glob("*.json")) if HISTORY_DIR.is_dir() else []
    entries = []
    for source in sorted(set(sources), key=lambda path: str(path).casefold()):
        try:
            stat = source.stat()
        except OSError:
            continue
        entries.append(f"{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}")
    return {"fileCount": len(entries), "signature": "|".join(entries)}


def trim_history(limit: int) -> None:
    with _SAVE_LOCK:
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
                if not isinstance(payload, dict):
                    continue
                raw_stamp = payload.get("generatedAt")
                if raw_stamp:
                    generated_at = _sort_timestamp(raw_stamp)
                else:
                    # stat() is only touched when the timestamp is absent, so a
                    # locked or already-removed file cannot drop a valid report.
                    generated_at = _sort_timestamp(None, fallback_mtime=source.stat().st_mtime)
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
                    _atomic_write_json(source, payload)
            except (OSError, json.JSONDecodeError):
                continue


def load_history() -> list[dict]:
    # HISTORY_DIR only. REPORTS_DIR root files are separate "저장된 리포트" entries
    # (served by /api/reports, kept forever, never trimmed) and used to also be
    # merged in here with a value-based dedup against their HISTORY_DIR twin. That
    # twin is exactly what `trim_history()` deletes once it ages past
    # `historyLimit`, and once it's gone the dedup key no longer matches, so the
    # permanent root copy would silently reappear as a "new" history item forever
    # — inflating the displayed/returned count past what `historyLimit` should
    # allow and defeating oldest-first trimming. Reading only HISTORY_DIR makes
    # the returned count and the trim policy refer to the same set of files.
    if not HISTORY_DIR.is_dir():
        return []

    items = []
    for source in HISTORY_DIR.glob("*.json"):
        if source == _favorites_path():
            continue
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        results = payload.get("results")
        if not isinstance(results, list):
            continue
        try:
            generated_at = payload.get("generatedAt") or datetime.fromtimestamp(
                source.stat().st_mtime, tz=timezone.utc
            ).isoformat(timespec="seconds")
        except OSError:
            continue
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            item = dict(result)
            item["id"] = f"{source.stem}:{index}"
            item["generatedAt"] = generated_at
            items.append(item)

    favorites = _load_favorites()
    legacy_counts: dict[str, int] = {}
    for item in sorted(items, key=lambda entry: _sort_timestamp(entry.get("generatedAt"))):
        original = str(item.get("sourceName") or item.get("name") or "")
        key = original.casefold()
        index = legacy_counts.get(key, 0)
        if "sourceName" not in item and index:
            item["name"] = _name_with_index(original, index)
        legacy_counts[key] = index + 1
    ordered = sorted(items, key=lambda item: _sort_timestamp(item.get("generatedAt")), reverse=True)
    for item in ordered:
        item["favorite"] = _item_key(item) in favorites
    limit = load_settings()["historyLimit"]
    if limit <= 0:
        return ordered
    favorite_items = [item for item in ordered if item["favorite"]]
    regular_items = [item for item in ordered if not item["favorite"]][:limit]
    return sorted(
        favorite_items + regular_items,
        key=lambda item: _sort_timestamp(item.get("generatedAt")),
        reverse=True,
    )


def set_favorite(item_id: str, favorite: bool) -> bool:
    with _SAVE_LOCK:
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
    if not stem or Path(stem).name != stem or any(token in stem for token in ("/", "\\", "..")):
        return False
    with _SAVE_LOCK:
        candidates = [REPORTS_DIR / f"{stem}.json", HISTORY_DIR / f"{stem}.json"]
        source = next((path for path in candidates if path.is_file()), None)
        if source is None:
            return False
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False
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
                _atomic_write_json(source, payload)
            return True
        except (OSError, json.JSONDecodeError):
            return False
