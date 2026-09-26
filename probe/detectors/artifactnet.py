"""Local inference adapter for the research-only ArtifactNet v9.4 model."""

from __future__ import annotations

from functools import lru_cache
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from ..audioio import Audio, load as load_audio
from ..detector_options import for_detector, option_labels

# The public model card fixes 44.1 kHz mono and 4-second segments, and the
# released ONNX is a single end-to-end graph, so there is no internal knob to
# expose. Only segment extraction and aggregation stay configurable.
SAMPLE_RATE = 44_100
SEGMENT_SECONDS = 4
SEGMENT_SAMPLES = SAMPLE_RATE * SEGMENT_SECONDS
SEGMENT_COUNT = 7
MIN_VALID_SEGMENTS = 4

AGGREGATION_LABELS = {
    "median": "segment median",
    "mean": "all segment mean",
    "top3": "top-3 segment mean",
    "max": "segment max",
}


def _resample(audio: Audio) -> np.ndarray:
    mono = audio.mono().astype(np.float32, copy=False)
    if audio.sample_rate == SAMPLE_RATE:
        return mono
    common = gcd(audio.sample_rate, SAMPLE_RATE)
    return resample_poly(mono, SAMPLE_RATE // common, audio.sample_rate // common).astype(np.float32)


def _segment_starts(length: int, count: int, selection: str) -> list[int]:
    if length <= SEGMENT_SAMPLES:
        return [0]
    tail = length - SEGMENT_SAMPLES
    if selection == "start":
        return [min(index * SEGMENT_SAMPLES, tail) for index in range(count)]
    return np.linspace(0, tail, count, dtype=np.int64).tolist()


def _aggregate(values: np.ndarray, aggregation: str) -> float:
    if values.size == 0:
        return 0.0
    if aggregation == "mean":
        return float(np.mean(values))
    if aggregation == "max":
        return float(np.max(values))
    if aggregation == "top3":
        top = min(3, values.size)
        return float(np.mean(np.sort(values)[-top:]))
    return float(np.median(values))


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
    options = for_detector("artifactnet")
    segment_count = int(options["segmentCount"])
    selection = str(options["segmentSelection"])
    aggregation = str(options["aggregation"])
    min_valid = int(options["minValidSegments"])
    threshold = float(options["threshold"])

    mono = _resample(audio)
    if mono.size == 0:
        raise ValueError("분석할 오디오 샘플이 없습니다.")

    starts = _segment_starts(mono.size, segment_count, selection)
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
    required = min(min_valid, len(segments))
    if values.size < required:
        raise ValueError(f"ArtifactNet 유효 구간이 부족합니다: {values.size}/{len(segments)}")
    aggregate = _aggregate(values, aggregation)
    return {
        "name": "artifactnet",
        "label": "ArtifactNet v9.4",
        "score": round(aggregate, 4),
        "aggregation": AGGREGATION_LABELS.get(aggregation, "segment median"),
        "segmentMean": round(float(np.mean(values)), 4),
        "segmentMedian": round(float(np.median(values)), 4),
        "segmentMax": round(float(np.max(values)), 4),
        "positiveFraction": round(float(np.mean(values >= threshold)), 4),
        "threshold": threshold,
        "verdict": "AI 우세" if aggregate >= threshold else "인간 우세",
        "options": {
            "segmentCount": segment_count,
            "segmentSelection": selection,
            "aggregation": aggregation,
            "minValidSegments": min_valid,
            "threshold": threshold,
        },
        "optionLabels": option_labels("artifactnet"),
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
