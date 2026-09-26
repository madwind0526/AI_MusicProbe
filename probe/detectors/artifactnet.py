"""Local inference adapter for the research-only ArtifactNet v9.4 model."""

from __future__ import annotations

from functools import lru_cache
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from ..audioio import Audio, load as load_audio

SAMPLE_RATE = 44_100
SEGMENT_SECONDS = 4
SEGMENT_SAMPLES = SAMPLE_RATE * SEGMENT_SECONDS
SEGMENT_COUNT = 7
MIN_VALID_SEGMENTS = 4


def _resample(audio: Audio) -> np.ndarray:
    mono = audio.mono().astype(np.float32, copy=False)
    if audio.sample_rate == SAMPLE_RATE:
        return mono
    common = gcd(audio.sample_rate, SAMPLE_RATE)
    return resample_poly(mono, SAMPLE_RATE // common, audio.sample_rate // common).astype(np.float32)


def _segment_starts(length: int) -> list[int]:
    if length <= SEGMENT_SAMPLES:
        return [0]
    return np.linspace(0, length - SEGMENT_SAMPLES, SEGMENT_COUNT, dtype=np.int64).tolist()


@lru_cache(maxsize=1)
def _session(model_path: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    return ort.InferenceSession(model_path, sess_options=options, providers=["CPUExecutionProvider"])


def _predict(chunk: np.ndarray, model_path: Path) -> float:
    session = _session(str(model_path.resolve()))
    output = session.run(None, {"audio": chunk.reshape(1, -1).astype(np.float32, copy=False)})[0]
    value = float(np.asarray(output).reshape(-1)[0])
    return float(np.clip(value, 0.0, 1.0)) if np.isfinite(value) else float("nan")


def analyze_audio(audio: Audio, model_path: Path) -> dict:
    mono = _resample(audio)
    if mono.size == 0:
        raise ValueError("분석할 오디오 샘플이 없습니다.")

    starts = _segment_starts(mono.size)
    segments = []
    for start in starts:
        chunk = mono[start : start + SEGMENT_SAMPLES]
        valid_samples = chunk.size
        if valid_samples < SEGMENT_SAMPLES:
            chunk = np.pad(chunk, (0, SEGMENT_SAMPLES - valid_samples))
        score = _predict(chunk, model_path)
        segment = {
            "startSeconds": round(start / SAMPLE_RATE, 3),
            "endSeconds": round(min((start + valid_samples) / SAMPLE_RATE, audio.duration_s), 3),
            "score": round(score, 4) if np.isfinite(score) else None,
        }
        if not np.isfinite(score):
            segment["error"] = "모델이 이 구간에서 유효한 점수를 반환하지 않았습니다."
        segments.append(segment)

    values = np.asarray([item["score"] for item in segments if item["score"] is not None], dtype=float)
    required = min(MIN_VALID_SEGMENTS, len(segments))
    if values.size < required:
        raise ValueError(f"ArtifactNet 유효 구간이 부족합니다: {values.size}/{len(segments)}")
    return {
        "name": "artifactnet",
        "label": "ArtifactNet v9.4",
        "score": round(float(np.median(values)), 4),
        "aggregation": "segment median",
        "segmentMean": round(float(np.mean(values)), 4),
        "segmentMedian": round(float(np.median(values)), 4),
        "segmentMax": round(float(np.max(values)), 4),
        "positiveFraction": round(float(np.mean(values >= 0.5)), 4),
        "validSegmentCount": int(values.size),
        "segmentCount": len(segments),
        "coverage": round(float(values.size / len(segments)), 4),
        "segments": segments,
        "modelVersion": "intrect/artifactnet-v9.4-full@e915f0dc",
        "notes": "44.1kHz 모노 4초 구간의 코덱 잔차를 분석하는 연구용 비상업 모델입니다.",
    }


def analyze_path(path: str | Path, model_path: Path) -> dict:
    return analyze_audio(load_audio(path), model_path)


def create_runner(model_path: Path):
    return lambda path: analyze_path(path, model_path)
