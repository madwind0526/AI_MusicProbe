"""SONICS SpecTTTra segment detector."""

from __future__ import annotations

from functools import lru_cache
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from ..audioio import Audio, load as load_audio
from ..detector_options import option_labels, for_detector

# Model-coupled preprocessing. These belong to the checkpoint and are not
# configurable, so they stay as module constants while the editable segment and
# aggregation controls live in `probe.detector_options`.
SAMPLE_RATE = 16_000
WINDOW_SECONDS = 5.0
HOP_SECONDS = 2.5
MAX_WINDOWS = 24

DEFAULT_TOP_K = 3
MIN_NORMALISATION_STD = 1e-6


def _resample(audio: Audio) -> np.ndarray:
    mono = audio.mono().astype(np.float32, copy=False)
    if audio.sample_rate == SAMPLE_RATE:
        return mono
    common = gcd(audio.sample_rate, SAMPLE_RATE)
    return resample_poly(mono, SAMPLE_RATE // common, audio.sample_rate // common).astype(np.float32)


def _window_starts(length: int, window: int, hop: int, max_windows: int) -> list[int]:
    if length <= window:
        return [0]
    starts = list(range(0, length - window + 1, hop))
    if starts[-1] != length - window:
        starts.append(length - window)
    if len(starts) <= max_windows:
        return starts
    indices = np.linspace(0, len(starts) - 1, max_windows, dtype=int)
    return [starts[index] for index in indices]


def _prepare(audio: Audio, max_windows: int, hop_seconds: float) -> tuple[np.ndarray, list[int]]:
    mono = _resample(audio)
    window = int(WINDOW_SECONDS * SAMPLE_RATE)
    hop = max(1, int(hop_seconds * SAMPLE_RATE))
    starts = _window_starts(mono.size, window, hop, max_windows)
    chunks = []
    for start in starts:
        chunk = mono[start : start + window]
        if chunk.size < window:
            chunk = np.pad(chunk, (0, window - chunk.size))
        std = float(np.std(chunk))
        if not np.isfinite(std) or std <= MIN_NORMALISATION_STD:
            chunk = np.zeros_like(chunk)
        else:
            chunk = chunk / std
        chunks.append(chunk.astype(np.float32, copy=False))
    return np.stack(chunks), starts


def _aggregate(scores: np.ndarray, aggregation: str, top_k: int) -> tuple[float, str]:
    """Song-level score from segment scores. The label is kept in the result so a
    saved report says which aggregation produced the number."""
    if scores.size == 0:
        return 0.0, "empty"
    if aggregation == "mean":
        return float(np.mean(scores)), "all segment mean"
    if aggregation == "median":
        return float(np.median(scores)), "segment median"
    count = max(1, min(int(top_k), scores.size))
    return float(np.mean(np.sort(scores)[-count:])), f"top-{count} segment mean"


@lru_cache(maxsize=1)
def _load_model(model_dir: str):
    import torch
    from sonics import HFAudioClassifier

    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    model = HFAudioClassifier.from_pretrained(model_dir, map_location="cpu")
    model.eval()
    return model


def analyze_audio(audio: Audio, model_dir: Path) -> dict:
    import torch

    options = for_detector("sonics")
    max_windows = int(options["maxWindows"])
    hop_seconds = float(options["hopSeconds"])
    threshold = float(options["threshold"])

    chunks, starts = _prepare(audio, max_windows, hop_seconds)
    model = _load_model(str(model_dir))
    values: list[float] = []
    with torch.inference_mode():
        for offset in range(0, len(chunks), 8):
            batch = torch.from_numpy(chunks[offset : offset + 8])
            logits = model(batch).squeeze(-1)
            values.extend(torch.sigmoid(logits).cpu().numpy().astype(float).tolist())

    scores = np.asarray(values, dtype=float)
    aggregate, aggregation_label = _aggregate(scores, str(options["aggregation"]), int(options["topK"]))
    segments = [
        {
            "startSeconds": round(start / SAMPLE_RATE, 3),
            "endSeconds": round(min((start / SAMPLE_RATE) + WINDOW_SECONDS, audio.duration_s), 3),
            "score": round(score, 4),
        }
        for start, score in zip(starts, scores, strict=True)
    ]
    return {
        "name": "sonics",
        "label": "SONICS / SpecTTTra gamma 5s",
        "score": round(aggregate, 4),
        "aggregation": aggregation_label,
        "segmentMean": round(float(np.mean(scores)), 4),
        "segmentMax": round(float(np.max(scores)), 4),
        "segmentMedian": round(float(np.median(scores)), 4),
        "positiveFraction": round(float(np.mean(scores >= threshold)), 4),
        "threshold": threshold,
        "verdict": "AI 우세" if aggregate >= threshold else "인간 우세",
        "options": {
            "maxWindows": max_windows,
            "hopSeconds": hop_seconds,
            "aggregation": str(options["aggregation"]),
            "topK": int(options["topK"]),
            "threshold": threshold,
        },
        "optionLabels": option_labels("sonics"),
        "segments": segments,
        "modelVersion": "awsaf49/sonics-spectttra-gamma-5s",
    }


def analyze_path(path: str | Path, model_dir: Path) -> dict:
    return analyze_audio(load_audio(path), model_dir)


def create_runner(model_dir: Path):
    return lambda path: analyze_path(path, model_dir)
