"""Remove scratch files that are no longer referenced by saved results."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import REPORTS_DIR, SCRATCH_DIR
from .visuals import visual_cache_path


def _referenced_audio_paths(reports_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    sources = list(reports_dir.glob("*.json"))
    history_dir = reports_dir / "history"
    if history_dir.is_dir():
        sources.extend(history_dir.glob("*.json"))
    for source in sources:
        if source.name == "favorites.json":
            continue
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            continue
        for result in results:
            raw_path = result.get("file") if isinstance(result, dict) else None
            if raw_path:
                resolved = Path(str(raw_path)).expanduser().resolve()
                paths[str(resolved).casefold()] = resolved
    return paths


def cleanup_scratch(
    scratch_dir: Path = SCRATCH_DIR,
    reports_dir: Path = REPORTS_DIR,
    grace_seconds: float = 3600.0,
) -> dict[str, int]:
    """Delete unreferenced uploads and stale visual cache files after a grace period."""
    referenced = _referenced_audio_paths(reports_dir)
    cutoff = time.time() - max(0.0, grace_seconds)
    deleted_uploads = 0
    deleted_visuals = 0

    upload_dir = scratch_dir / "uploads"
    if upload_dir.is_dir():
        for path in upload_dir.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime <= cutoff and str(path.resolve()).casefold() not in referenced:
                    path.unlink()
                    deleted_uploads += 1
            except OSError:
                continue

    visual_dir = scratch_dir / "visuals"
    expected_visuals: set[str] = set()
    for path in referenced.values():
        if not path.is_file():
            continue
        try:
            for kind in ("waveform", "spectrogram"):
                expected_visuals.add(str(visual_cache_path(path, kind, visual_dir).resolve()).casefold())
        except OSError:
            continue
    if visual_dir.is_dir():
        for path in visual_dir.glob("*.png"):
            try:
                if path.stat().st_mtime <= cutoff and str(path.resolve()).casefold() not in expected_visuals:
                    path.unlink()
                    deleted_visuals += 1
            except OSError:
                continue

    return {"uploads": deleted_uploads, "visuals": deleted_visuals}
