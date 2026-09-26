"""Local inference for the MIT-licensed lofcz vocoder fakeprint model."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.ndimage import minimum_filter1d
from scipy.signal import resample_poly

from ..audioio import Audio, load as load_audio
from ..detector_options import for_detector, option_labels

# Fakeprint is defined by these constants, so they stay locked to the model
# description while the editable analysis window and aggregation live in
# `probe.detector_options`.
SAMPLE_RATE = 16_000
N_FFT = 8_192
HOP = N_FFT // 2
FREQ_MIN = 1_000
FREQ_MAX = 8_000
HULL_SIZE = 10
MAX_DB = 5.0
MIN_DB = -45.0
MAX_DURATION_S = 300
SEGMENT_DURATION_S = 30
SEGMENT_HOP_S = 15


def _resample(mono: np.ndarray, source_rate: int) -> np.ndarray:
    if source_rate == SAMPLE_RATE:
        return np.asarray(mono, dtype=np.float32)
    common = int(np.gcd(source_rate, SAMPLE_RATE))
    converted = resample_poly(mono, SAMPLE_RATE // common, source_rate // common)
    return np.asarray(converted, dtype=np.float32)


def _fakeprint(samples: np.ndarray) -> np.ndarray:
    if samples.size < N_FFT:
        samples = np.pad(samples, (0, N_FFT - samples.size))
    padded = np.pad(samples, (N_FFT // 2, N_FFT // 2), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP]
    window = np.hanning(N_FFT + 1)[:-1].astype(np.float32)
    power = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    mean_db = 10.0 * np.log10(np.clip(power.mean(axis=0), 1e-10, 1e6))
    freqs = np.linspace(0, SAMPLE_RATE / 2, (N_FFT // 2) + 1)
    selected = mean_db[(freqs >= FREQ_MIN) & (freqs <= FREQ_MAX)]
    hull = np.clip(minimum_filter1d(selected, size=HULL_SIZE, mode="nearest"), MIN_DB, None)
    residue = np.clip(selected - hull, 0.0, MAX_DB)
    return np.asarray(residue / (float(residue.max()) + 1e-6), dtype=np.float32)


@lru_cache(maxsize=4)
def _session(model_path: str):
    import onnxruntime as ort

    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def _predict(samples: np.ndarray, model_path: Path) -> float:
    session = _session(str(model_path.resolve()))
    model_input = session.get_inputs()[0]
    features = _fakeprint(samples)
    expected = int(model_input.shape[1])
    if features.size != expected:
        features = np.interp(
            np.linspace(0.0, 1.0, expected),
            np.linspace(0.0, 1.0, features.size),
            features,
        ).astype(np.float32)
    output = session.run(None, {model_input.name: features.reshape(1, -1)})[0]
    return float(np.asarray(output).reshape(-1)[0])


def _segment_starts(length: int) -> list[int]:
    window = SEGMENT_DURATION_S * SAMPLE_RATE
    hop = SEGMENT_HOP_S * SAMPLE_RATE
    if length <= window:
        return [0]
    starts = list(range(0, length - window + 1, hop))
    tail = length - window
    if starts[-1] != tail:
        starts.append(tail)
    return starts


#: A long track would otherwise cost one full-length prediction per window, so
#: spaced sampling is capped. The cap is reported instead of applied silently.
MAX_EVEN_WINDOWS = 6


def _even_window_starts(length: int, window: int) -> list[int]:
    """Spaced windows of `window` samples covering the whole track evenly."""
    if length <= window:
        return [0]
    count = max(1, min(MAX_EVEN_WINDOWS, -(-length // window)))
    return np.linspace(0, length - window, count, dtype=np.int64).tolist()


def analyze_audio(audio: Audio, model_path: Path) -> dict:
    options = for_detector("lofcz")
    max_duration_s = int(options["maxDurationS"])
    position = str(options["analysisPosition"])
    aggregation = str(options["aggregation"])
    threshold = float(options["threshold"])

    mono = _resample(audio.mono(), audio.sample_rate)
    if mono.size == 0:
        raise ValueError("분석할 오디오 샘플이 없습니다.")

    analysis_window = max_duration_s * SAMPLE_RATE
    full_score = _predict(mono[:analysis_window], model_path)

    # `start` scores one window from the beginning, so the song-level number is
    # that single score. `even` scores spaced windows across the whole track and
    # combines them with the configured aggregate. Only the 30-second diagnostic
    # timeline is capped, so `even` really does sample the entire track.
    timeline = mono[:MAX_DURATION_S * SAMPLE_RATE]
    even_scores: list[float] = []
    even_windows: list[dict] = []
    even_capped = False
    if position == "even":
        starts = _even_window_starts(mono.size, analysis_window)
        even_capped = len(starts) >= MAX_EVEN_WINDOWS and mono.size > analysis_window * MAX_EVEN_WINDOWS
        for start in starts:
            end = min(start + analysis_window, mono.size)
            score = _predict(mono[start:end], model_path)
            even_scores.append(score)
            even_windows.append({
                "startS": round(start / SAMPLE_RATE, 2),
                "endS": round(end / SAMPLE_RATE, 2),
                "score": round(score, 4),
            })

    if even_scores:
        values = np.asarray(even_scores, dtype=float)
        track_score = float(np.median(values)) if aggregation == "median" else float(np.mean(values))
        aggregation_label = "even window median" if aggregation == "median" else "even window mean"
    else:
        values = None
        track_score = full_score
        aggregation_label = "single window score"

    window = SEGMENT_DURATION_S * SAMPLE_RATE
    segments = []
    for start in _segment_starts(timeline.size):
        chunk = timeline[start : start + window]
        score = _predict(chunk, model_path)
        segments.append(
            {
                "startS": round(start / SAMPLE_RATE, 2),
                "endS": round((start + chunk.size) / SAMPLE_RATE, 2),
                "score": round(score, 4),
            }
        )

    segment_values = np.asarray([item["score"] for item in segments], dtype=float)
    result = {
        "name": "lofcz",
        "label": "Vocoder fakeprint",
        "score": round(track_score, 4),
        "aggregation": aggregation_label,
        "segmentMean": round(float(segment_values.mean()), 4),
        "segmentMax": round(float(segment_values.max()), 4),
        "segmentMin": round(float(segment_values.min()), 4),
        "windowScore": round(full_score, 4),
        "threshold": threshold,
        "verdict": "AI 우세" if track_score >= threshold else "인간 우세",
        "options": {
            "maxDurationS": max_duration_s,
            "analysisPosition": position,
            "aggregation": aggregation,
            "threshold": threshold,
        },
        "optionLabels": option_labels("lofcz"),
        "segments": segments,
        "modelVersion": "lofcz-ai-music-detector-v1",
        "notes": "신경 vocoder의 1~8kHz 주파수 흔적을 측정합니다.",
    }
    if values is not None:
        result["evenWindowCount"] = int(values.size)
        result["evenWindowMean"] = round(float(values.mean()), 4)
        result["evenWindowMedian"] = round(float(np.median(values)), 4)
        result["evenWindows"] = even_windows
        if even_capped:
            result["evenWindowNote"] = f"구간 수 상한({MAX_EVEN_WINDOWS}개)에 걸려 곡 전체를 고르게 덮지 못했습니다."
    return result


def analyze_path(path: str | Path, model_path: Path) -> dict:
    return analyze_audio(load_audio(path), model_path)


def create_runner(model_path: Path):
    def run(path: str | Path) -> dict:
        return analyze_path(path, model_path)

    return run
