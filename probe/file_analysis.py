"""File-oriented analysis used by the public API and the WebUI."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from . import dsp
from . import detector_options
from .audioio import AudioToolError, is_audio_file, load as load_audio
from .detectors import DETECTORS


def expand_inputs(paths: Iterable[str | Path], recursive: bool = True) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        candidates: Iterable[Path]
        if path.is_dir():
            candidates = path.rglob("*") if recursive else path.glob("*")
        else:
            candidates = [path]
        for candidate in candidates:
            if not is_audio_file(candidate):
                continue
            resolved = candidate.resolve()
            key = str(resolved).casefold()
            if key not in seen:
                seen.add(key)
                files.append(resolved)
    return sorted(files, key=lambda item: str(item).casefold())


def _conclusion(score: float) -> str:
    if score < 20:
        return "AI 생성 흔적이 거의 없음"
    if score < 50:
        return "AI 생성 흔적이 매우 약함"
    if score < 80:
        return "AI 생성 흔적이 비교적 약함"
    if score < 90:
        return "AI 생성 흔적이 비교적 강함"
    return "AI 생성 흔적이 매우 강함"


#: Floors a raw detector score before it enters a geometric combination, so a
#: detector that returns a near-zero probability cannot zero out the whole score.
GEOMETRIC_FLOOR = 1e-6

METHOD_LABELS = {
    "geometric": "detector-geometric-mean-v1",
    "arithmetic": "detector-arithmetic-mean-v1",
    "median": "detector-median-v1",
    "weightedGeometric": "detector-weighted-geometric-mean-v1",
    "robustMean": "detector-robust-mean-v1",
}

#: Modified Z-score cutoff (Iglewicz & Hoaglin's rule of thumb) for "robustMean": a
#: detector further than this from the group's median (in MAD units) is dropped
#: before averaging the rest. MAD is used instead of mean/std because with only a
#: handful of detectors, an actual outlier inflates a plain standard deviation
#: enough to hide itself from a mean/std-based rule (verified against this app's
#: own 3-detector case: a lofcz score of 0 next to ~0.85/~0.99 survives a 3-sigma
#: mean/std cut, and even 1-sigma then starts dropping detectors that plainly agree).
ROBUST_Z_THRESHOLD = 3.5


def _robust_mean(values: np.ndarray, names: list[str]) -> tuple[float, list[str]]:
    if values.size <= 2:
        return float(np.mean(values)), []
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0.0:
        keep = np.isclose(values, median, rtol=0.0, atol=1e-12)
        if not bool(keep.any()) or bool(keep.all()):
            return float(np.mean(values)), []
        outliers = [name for name, kept in zip(names, keep) if not kept]
        return float(np.mean(values[keep])), outliers
    z = 0.6745 * (values - median) / mad
    keep = np.abs(z) <= ROBUST_Z_THRESHOLD
    if not bool(keep.any()):
        return float(np.mean(values)), []
    outliers = [name for name, kept in zip(names, keep) if not kept]
    return float(np.mean(values[keep])), outliers


def _combine(values: np.ndarray, names: list[str], method: str, weights: dict[str, float]) -> float:
    if method == "arithmetic":
        return float(np.mean(values))
    if method == "median":
        return float(np.median(values))
    if method == "weightedGeometric":
        weight_array = np.asarray([max(0.0, float(weights.get(name, 1.0))) for name in names], dtype=float)
        if float(weight_array.sum()) <= 0:
            raise ValueError("Total에 반영할 가중치가 없습니다.")
        normalized = weight_array / weight_array.sum()
        return float(np.exp(np.sum(normalized * np.log(np.maximum(values, GEOMETRIC_FLOOR)))))
    if method == "robustMean":
        return _robust_mean(values, names)[0]
    return float(np.prod(np.maximum(values, GEOMETRIC_FLOOR)) ** (1.0 / values.size))


def _score(detector_results: list[dict], ensemble: dict | None = None) -> tuple[float | None, float, str, dict]:
    settings = ensemble if isinstance(ensemble, dict) else detector_options.current()["ensemble"]
    method = str(settings.get("method", "robustMean"))
    weights = settings.get("weights") if isinstance(settings.get("weights"), dict) else {}

    valid = [
        item for item in detector_results
        if isinstance(item.get("score"), (int, float)) and math.isfinite(float(item["score"]))
    ]
    if not valid:
        return None, 0.0, "사용 가능한 학습 기반 탐지기가 없어 total 점수를 계산하지 못했습니다.", {}

    scores = {item["name"]: max(0.0, min(1.0, float(item["score"]))) for item in valid}
    included = [item for item in valid if item.get("includedInTotal", True)]
    if method == "weightedGeometric":
        included = [item for item in included if max(0.0, float(weights.get(item["name"], 1.0))) > 0]
    names = [item["name"] for item in included]
    if not names:
        excluded = ", ".join(sorted(scores)) or "없음"
        return None, 0.0, f"Total 반영 탐지기가 없어 점수를 계산하지 못했습니다. (평가만 또는 가중치 0: {excluded})", {}

    values = np.asarray([scores[name] for name in names], dtype=float)
    outliers_excluded: list[str] = []
    agreement_values = values
    if method == "robustMean":
        raw, outliers_excluded = _robust_mean(values, names)
        if outliers_excluded:
            agreement_values = np.asarray(
                [value for name, value in zip(names, values) if name not in outliers_excluded],
                dtype=float,
            )
    else:
        raw = _combine(values, names, method, weights)
    total = round(raw * 100.0, 1)
    agreement = 1.0 if agreement_values.size == 1 else max(0.0, 1.0 - float(np.std(agreement_values)) * 2.0)
    confidence = round(abs(raw - 0.5) * 2.0 * agreement * 100.0, 1)
    excluded = sorted(name for name in scores if name not in names)
    return total, confidence, _conclusion(total), {
        "method": METHOD_LABELS.get(method, "detector-geometric-mean-v1"),
        "inputs": {name: round(value, 4) for name, value in scores.items()},
        "included": names,
        "excluded": excluded,
        "outliersExcluded": outliers_excluded,
        "weights": {name: round(float(weights.get(name, 1.0)), 3) for name in names} if method == "weightedGeometric" else {},
        "agreement": round(agreement, 4),
    }


def analyze_file(path: str | Path) -> dict:
    file_path = Path(path).resolve()
    audio = load_audio(file_path)
    profile = dsp.analyze(audio)
    detector_results = []
    detector_errors = []
    settings = detector_options.current()
    for detector in DETECTORS.values():
        if not detector.active:
            continue
        try:
            result = detector.run(file_path)  # type: ignore[misc]
            # A detector that failed to return a score still appears in the
            # report, so an evaluation-only or broken slot is never invisible.
            result.setdefault("includedInTotal", bool(settings["detectors"].get(detector.name, {}).get("includedInTotal", True)))
            detector_results.append(result)
        except Exception as error:  # noqa: BLE001
            detector_errors.append({"name": detector.name, "message": str(error)})

    total, confidence, conclusion, score_components = _score(detector_results, settings["ensemble"])
    return {
        "file": str(file_path),
        "name": file_path.name,
        "status": "completed",
        "parameters": profile,
        "detectors": detector_results,
        "detectorErrors": detector_errors,
        "totalScore": total,
        "confidence": confidence,
        "conclusion": conclusion,
        "detectorSettings": {
            "ensemble": settings["ensemble"],
            "detectors": settings["detectors"],
        },
        "scoreInfo": {
            "scale": "0-100",
            "meaning": "높을수록 AI 생성 과정과 일치하는 음향 흔적이 강합니다.",
            "calibration": "provisional-ensemble-v1",
            "isProbability": False,
            "components": score_components,
        },
    }


def analyze_files(
    paths: Iterable[str | Path],
    recursive: bool = True,
    on_progress: Callable[[int, int, Path | None], None] | None = None,
) -> dict:
    files = expand_inputs(paths, recursive=recursive)
    if on_progress is not None:
        on_progress(0, len(files), None)
    results = []
    for index, path in enumerate(files, start=1):
        if on_progress is not None:
            on_progress(index, len(files), path)
        try:
            results.append(analyze_file(path))
        except Exception as error:  # noqa: BLE001
            results.append(
                {
                    "file": str(path),
                    "name": path.name,
                    "status": "failed",
                    "error": str(error),
                    "totalScore": None,
                }
            )
    completed = sum(item["status"] == "completed" for item in results)
    return {
        "tool": "ai-music-probe",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputCount": len(files),
        "results": results,
        "summary": {
            "completed": completed,
            "failed": len(results) - completed,
        },
    }
