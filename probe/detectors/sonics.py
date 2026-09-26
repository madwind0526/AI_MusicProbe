"""SONICS SpecTTTra segment detector."""

from __future__ import annotations

from functools import lru_cache
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from ..audioio import Audio, load as load_audio

SAMPLE_RATE = 16_000
WINDOW_SECONDS = 5.0
HOP_SECONDS = 2.5
MAX_WINDOWS = 24


def _resample(audio: Audio) -> np.ndarray:
    mono = audio.mono().astype(np.float32, copy=False)
    if audio.sample_rate == SAMPLE_RATE:
        return mono
    common = gcd(audio.sample_rate, SAMPLE_RATE)
    return resample_poly(mono, SAMPLE_RATE // common, audio.sample_rate // common).astype(np.float32)


def _window_starts(length: int, window: int, hop: int) -> list[int]:
    if length <= window:
        return [0]
    starts = list(range(0, length - window + 1, hop))
    if starts[-1] != length - window:
        starts.append(length - window)
    if len(starts) <= MAX_WINDOWS:
        return starts
    indices = np.linspace(0, len(starts) - 1, MAX_WINDOWS, dtype=int)
    return [starts[index] for index in indices]


def _prepare(audio: Audio) -> tuple[np.ndarray, list[int]]:
    mono = _resample(audio)
    window = int(WINDOW_SECONDS * SAMPLE_RATE)
    hop = int(HOP_SECONDS * SAMPLE_RATE)
    starts = _window_starts(mono.size, window, hop)
    chunks = []
    for start in starts:
        chunk = mono[start : start + window]
        if chunk.size < window:
            chunk = np.pad(chunk, (0, window - chunk.size))
        chunk = chunk / max(float(np.std(chunk)), 1e-6)
        chunks.append(chunk.astype(np.float32, copy=False))
    return np.stack(chunks), starts


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

    chunks, starts = _prepare(audio)
    model = _load_model(str(model_dir))
    values: list[float] = []
    with torch.inference_mode():
        for offset in range(0, len(chunks), 8):
            batch = torch.from_numpy(chunks[offset : offset + 8])
            logits = model(batch).squeeze(-1)
            values.extend(torch.sigmoid(logits).cpu().numpy().astype(float).tolist())

    scores = np.asarray(values, dtype=float)
    top_count = min(3, scores.size)
    aggregate = float(np.mean(np.sort(scores)[-top_count:]))
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
        "aggregation": "top-3 segment mean",
        "segmentMean": round(float(np.mean(scores)), 4),
        "segmentMax": round(float(np.max(scores)), 4),
        "positiveFraction": round(float(np.mean(scores >= 0.5)), 4),
        "segments": segments,
        "modelVersion": "awsaf49/sonics-spectttra-gamma-5s",
    }


def analyze_path(path: str | Path, model_dir: Path) -> dict:
    return analyze_audio(load_audio(path), model_dir)


def create_runner(model_dir: Path):
    return lambda path: analyze_path(path, model_dir)
