"""Recompute totalScore/confidence/conclusion/scoreInfo for every stored analysis result, from its
already-measured detector scores - no audio is re-read and no model reruns. Use this after changing
the Total combination method (see probe/detector_options.py's ENSEMBLE_METHODS) so past results
reflect the new method instead of staying frozen with whatever was active when they were first
analyzed.

    python scripts/recompute_totals.py
    python scripts/recompute_totals.py --method robustMean
    python scripts/recompute_totals.py --extra-dir "C:\\Claude\\SongYUE2\\library\\AI-MusicProbe"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probe.config import REPORTS_DIR  # noqa: E402
from probe.detector_options import DEFAULT_ENSEMBLE, ENSEMBLE_METHODS  # noqa: E402
from probe.file_analysis import _score  # noqa: E402

HISTORY_DIR = REPORTS_DIR / "history"


def _stored_ensemble(result: dict, method: str) -> dict:
    detector_settings = result.get("detectorSettings")
    saved = detector_settings.get("ensemble") if isinstance(detector_settings, dict) else None
    weights = saved.get("weights") if isinstance(saved, dict) and isinstance(saved.get("weights"), dict) else {}
    return {"method": method, "weights": dict(weights)}


def _atomic_write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def _recompute_result(result: dict, method: str) -> bool:
    """Mutates `result` in place with the new Total; returns True if anything actually changed."""
    if result.get("status") != "completed":
        return False
    detectors = result.get("detectors")
    if not isinstance(detectors, list) or not detectors:
        return False
    ensemble = _stored_ensemble(result, method)
    before = json.dumps({
        "totalScore": result.get("totalScore"),
        "confidence": result.get("confidence"),
        "conclusion": result.get("conclusion"),
        "components": (result.get("scoreInfo") or {}).get("components"),
        "ensemble": (result.get("detectorSettings") or {}).get("ensemble"),
    }, ensure_ascii=False, sort_keys=True)
    total, confidence, conclusion, components = _score(detectors, ensemble)
    if total is None:
        return False
    result["totalScore"] = total
    result["confidence"] = confidence
    result["conclusion"] = conclusion
    score_info = result.setdefault("scoreInfo", {})
    score_info["components"] = components
    detector_settings = result.setdefault("detectorSettings", {})
    detector_settings["ensemble"] = ensemble
    after = json.dumps({
        "totalScore": total,
        "confidence": confidence,
        "conclusion": conclusion,
        "components": components,
        "ensemble": ensemble,
    }, ensure_ascii=False, sort_keys=True)
    return before != after


def _process_wrapped(path: Path, method: str, dry_run: bool = False) -> int:
    """ai-music-probe's own storage: {"results": [ {..one result..}, ... ]}."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    results = payload.get("results")
    if not isinstance(results, list):
        return 0
    updated = sum(1 for result in results if isinstance(result, dict) and _recompute_result(result, method))
    if updated and not dry_run:
        _atomic_write_json(path, payload)
    return updated


def _process_single(path: Path, method: str, dry_run: bool = False) -> int:
    """A directory of bare result dicts (one per file) - e.g. SongYUE2's library/AI-MusicProbe/."""
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(result, dict) or not _recompute_result(result, method):
        return 0
    if not dry_run:
        _atomic_write_json(path, result)
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    methods = [name for name, _label in ENSEMBLE_METHODS]
    parser.add_argument("--method", choices=methods, default=DEFAULT_ENSEMBLE["method"], help="Total 결합 방식 (기본: 현재 코드 기본값)")
    parser.add_argument("--dry-run", action="store_true", help="파일을 저장하지 않고 변경될 결과 수만 확인")
    parser.add_argument(
        "--extra-dir",
        action="append",
        default=[],
        help="추가로 훑을 폴더: 감싸지 않은 단일 result dict *.json들이 있는 곳 (예: SongYUE2의 library/AI-MusicProbe)",
    )
    args = parser.parse_args()
    updated = 0
    scanned = 0
    if REPORTS_DIR.is_dir():
        for path in REPORTS_DIR.glob("*.json"):
            scanned += 1
            updated += _process_wrapped(path, args.method, args.dry_run)
    if HISTORY_DIR.is_dir():
        for path in HISTORY_DIR.glob("*.json"):
            if path.name == "favorites.json":
                continue
            scanned += 1
            updated += _process_wrapped(path, args.method, args.dry_run)
    for extra in args.extra_dir:
        extra_path = Path(extra)
        if not extra_path.is_dir():
            print(f"건너뜀 (폴더 없음): {extra_path}")
            continue
        for path in extra_path.glob("*.json"):
            scanned += 1
            updated += _process_single(path, args.method, args.dry_run)

    action = "변경 예정" if args.dry_run else "갱신"
    print(f"방식: {args.method}  ·  파일 {scanned}개 확인  ·  결과 {updated}개 {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
