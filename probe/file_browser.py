"""Local filesystem browsing for the WebUI pickers."""

from __future__ import annotations

import os
from pathlib import Path

from .config import AUDIO_EXTENSIONS, ROOT

DRIVES_TOKEN = "::drives"
SKIPPED_DIRECTORIES = {"$RECYCLE.BIN", "System Volume Information"}


def _available_drives() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    return [Path(f"{letter}:\\") for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]


def browse_directory(raw_path: str | None = None) -> dict:
    """Return visible folders and supported audio files for one local directory."""
    if raw_path == DRIVES_TOKEN:
        entries = [
            {"name": str(drive), "path": str(drive), "type": "directory"}
            for drive in _available_drives()
        ]
        return {
            "startPath": str(ROOT.resolve()),
            "path": DRIVES_TOKEN,
            "displayPath": "내 PC",
            "parent": None,
            "entries": entries,
        }

    target = Path(raw_path).expanduser() if raw_path else ROOT
    try:
        target = target.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("폴더를 찾을 수 없습니다.") from exc
    if not target.is_dir():
        raise ValueError("선택한 경로는 폴더가 아닙니다.")

    entries = []
    try:
        children = list(target.iterdir())
    except OSError as exc:
        raise ValueError("이 폴더를 열 권한이 없습니다.") from exc

    for child in children:
        if child.name.startswith(".") or child.name in SKIPPED_DIRECTORIES:
            continue
        try:
            if child.is_dir():
                entries.append({"name": child.name, "path": str(child), "type": "directory"})
            elif child.is_file() and child.suffix.lower() in AUDIO_EXTENSIONS:
                stat = child.stat()
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "type": "file",
                    "size": stat.st_size,
                })
        except OSError:
            continue

    entries.sort(key=lambda item: (item["type"] != "directory", item["name"].casefold()))
    parent = target.parent
    parent_path = DRIVES_TOKEN if parent == target else str(parent)
    return {
        "startPath": str(ROOT.resolve()),
        "path": str(target),
        "displayPath": str(target),
        "parent": parent_path,
        "entries": entries,
    }
