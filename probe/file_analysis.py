"""File-oriented analysis used by the public API and the WebUI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

from . import dsp
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


def _score(detector_results: list[dict]) -> tuple[float | None, float, str, dict]:
    valid = [item for item in detector_results if isinstance(item.get("score"), (int, float))]
    if not valid:
        return None, 0.0, "사용 가능한 학습 기반 탐지기가 없어 total 점수를 계산하지 못했습니다.", {}

    scores = {item["name"]: max(0.0, min(1.0, float(item["score"]))) for item in valid}
    values = np.asarray(list(scores.values()), dtype=float)
    # The geometric mean rewards corroboration and prevents one saturated
    # detector from deciding the entire result. Corpus calibration follows later.
    raw = float(np.prod(np.maximum(values, 1e-6)) ** (1.0 / values.size))
    total = round(raw * 100.0, 1)
    agreement = 1.0 if values.size == 1 else max(0.0, 1.0 - float(np.std(values)) * 2.0)
    confidence = round(abs(raw - 0.5) * 2.0 * agreement * 100.0, 1)
    return total, confidence, _conclusion(total), {
        "method": "detector-geometric-mean-v1",
        "inputs": {name: round(value, 4) for name, value in scores.items()},
        "agreement": round(agreement, 4),
    }


def analyze_file(path: str | Path) -> dict:
    file_path = Path(path).resolve()
    audio = load_audio(file_path)
    profile = dsp.analyze(audio)
    detector_results = []
    detector_errors = []
    for detector in DETECTORS.values():
        if not detector.active:
            continue
        try:
            result = detector.run(file_path)  # type: ignore[misc]
            detector_results.append(result)
        except Exception as error:  # noqa: BLE001
            detector_errors.append({"name": detector.name, "message": str(error)})

    total, confidence, conclusion, score_components = _score(detector_results)
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
        "scoreInfo": {
            "scale": "0-100",
            "meaning": "높을수록 AI 생성 과정과 일치하는 음향 흔적이 강합니다.",
            "calibration": "provisional-ensemble-v1",
            "isProbability": False,
            "components": score_components,
        },
    }


def analyze_files(paths: Iterable[str | Path], recursive: bool = True) -> dict:
    files = expand_inputs(paths, recursive=recursive)
    results = []
    for path in files:
        try:
            results.append(analyze_file(path))
        except (AudioToolError, ValueError, OSError) as error:
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
