"""Segment selection and aggregation math behind the per-detector settings.

These functions are what the per-detector options actually change, so they get
tested directly instead of through a model run.
"""

import numpy as np
import pytest
from pathlib import Path

from probe.audioio import Audio, AudioMeta
from probe.detectors import artifactnet, lofcz, sonics
from probe.detectors.artifactnet import SEGMENT_SAMPLES, _aggregate as artifactnet_aggregate, _segment_starts as artifactnet_starts
from probe.detectors.lofcz import _even_window_starts
from probe.detectors.sonics import _aggregate as sonics_aggregate, _window_starts

RATE = 16_000


# --- SONICS ---------------------------------------------------------------

def test_sonics_defaults_keep_the_top_three_segments() -> None:
    scores = np.asarray([0.1, 0.95, 0.2, 0.9, 0.05])

    value, label = sonics_aggregate(scores, "topk", 3)

    assert label == "top-3 segment mean"
    assert value == pytest.approx((0.95 + 0.9 + 0.2) / 3)


def test_sonics_top_k_never_exceeds_the_segment_count() -> None:
    value, label = sonics_aggregate(np.asarray([0.4, 0.6]), "topk", 5)

    assert label == "top-2 segment mean"
    assert value == pytest.approx(0.5)


def test_sonics_top_one_ignores_every_other_segment() -> None:
    value, label = sonics_aggregate(np.asarray([0.99, 0.1, 0.1]), "topk", 1)

    assert label == "top-1 segment mean"
    assert value == pytest.approx(0.99)


def test_sonics_mean_and_median_differ_on_a_single_hot_segment() -> None:
    scores = np.asarray([1.0, 0.1, 0.1, 0.1, 0.1])

    mean_value, mean_label = sonics_aggregate(scores, "mean", 3)
    median_value, median_label = sonics_aggregate(scores, "median", 3)

    assert mean_label == "all segment mean"
    assert median_label == "segment median"
    assert mean_value == pytest.approx(0.28)
    assert median_value == pytest.approx(0.1)


def test_sonics_max_windows_caps_and_resamples_the_start_positions() -> None:
    starts = _window_starts(length=600 * RATE, window=5 * RATE, hop=int(2.5 * RATE), max_windows=8)

    assert len(starts) == 8
    assert starts[0] == 0
    assert starts == sorted(starts)


def test_sonics_short_audio_is_scored_from_a_single_window() -> None:
    assert _window_starts(length=3 * RATE, window=5 * RATE, hop=2 * RATE, max_windows=24) == [0]


def test_sonics_degenerate_window_is_silenced_instead_of_amplified() -> None:
    samples = np.full((5 * RATE, 1), 0.001, dtype=np.float32)
    meta = AudioMeta(Path("constant.wav"), "pcm_f32le", RATE, 1, 5.0, 32, False)

    chunks, _starts = sonics._prepare(Audio(samples, RATE, meta), max_windows=1, hop_seconds=2.5)

    assert np.count_nonzero(chunks) == 0


# --- ArtifactNet ----------------------------------------------------------

def test_artifactnet_even_selection_matches_the_public_protocol() -> None:
    length = 200 * 44_100
    tail = length - SEGMENT_SAMPLES
    starts = artifactnet_starts(length, 7, "even")

    assert starts == [index * tail // 6 for index in range(7)]
    assert starts[0] == 0
    assert starts[-1] == length - SEGMENT_SAMPLES


def test_artifactnet_start_selection_walks_from_the_beginning() -> None:
    starts = artifactnet_starts(300 * 44_100, 5, "start")

    assert starts[:3] == [0, SEGMENT_SAMPLES, 2 * SEGMENT_SAMPLES]
    assert starts == sorted(starts)


def test_artifactnet_start_selection_clamps_to_the_last_full_segment() -> None:
    starts = artifactnet_starts(6 * SEGMENT_SAMPLES, 5, "start")

    assert starts == [index * SEGMENT_SAMPLES for index in range(5)]


def test_artifactnet_start_selection_never_duplicates_the_tail() -> None:
    starts = artifactnet_starts(5 * SEGMENT_SAMPLES, 11, "start")

    assert starts == [index * SEGMENT_SAMPLES for index in range(5)]
    assert len(starts) == len(set(starts))


def test_artifactnet_median_is_the_documented_default() -> None:
    values = np.asarray([0.01, 0.2, 0.3, 0.4, 0.9])

    assert artifactnet_aggregate(values, "median") == pytest.approx(0.3)
    assert artifactnet_aggregate(values, "mean") == pytest.approx(0.362)
    assert artifactnet_aggregate(values, "max") == pytest.approx(0.9)
    assert artifactnet_aggregate(values, "top3") == pytest.approx((0.4 + 0.9 + 0.3) / 3)


def test_artifactnet_reports_a_relaxed_minimum_for_short_audio(monkeypatch) -> None:
    samples = np.zeros((2 * 44_100, 1), dtype=np.float32)
    meta = AudioMeta(Path("short.wav"), "pcm_f32le", 44_100, 1, 2.0, 32, False)
    monkeypatch.setattr(artifactnet, "for_detector", lambda _name: {
        "segmentCount": 11,
        "segmentSelection": "even",
        "aggregation": "top3",
        "minValidSegments": 4,
        "threshold": 0.5,
        "levelNormalize": False,
    })
    monkeypatch.setattr(artifactnet, "option_labels", lambda _name: {})
    monkeypatch.setattr(artifactnet, "_predict", lambda _chunk, _path: 0.25)

    result = artifactnet.analyze_audio(Audio(samples, 44_100, meta), Path("model.onnx"))

    assert result["effectiveMinValidSegments"] == 1
    assert result["minimumAdjustedForShortAudio"] is True
    assert result["validSegmentCount"] == 1


# --- lofcz ----------------------------------------------------------------

def test_even_window_sampling_covers_the_whole_track() -> None:
    starts = _even_window_starts(length=600 * RATE, window=300 * RATE)

    assert starts == [0, 300 * RATE]


def test_even_window_sampling_is_capped_so_runtime_stays_bounded() -> None:
    starts = _even_window_starts(length=4 * 3600 * RATE, window=60 * RATE)

    assert len(starts) == 6
    assert starts[0] == 0
    assert max(starts) == 4 * 3600 * RATE - 60 * RATE


def test_even_window_sampling_returns_one_window_for_short_audio() -> None:
    assert _even_window_starts(length=100 * RATE, window=300 * RATE) == [0]


def test_lofcz_segment_statistics_use_the_scoring_windows(monkeypatch) -> None:
    samples = np.zeros((100 * RATE, 1), dtype=np.float32)
    meta = AudioMeta(Path("long.wav"), "pcm_f32le", RATE, 1, 100.0, 32, False)
    calls = []
    monkeypatch.setattr(lofcz, "for_detector", lambda _name: {
        "maxDurationS": 30,
        "analysisPosition": "even",
        "aggregation": "mean",
        "threshold": 0.5,
    })
    monkeypatch.setattr(lofcz, "option_labels", lambda _name: {})

    def predict(chunk, _path):
        calls.append(chunk.size)
        return len(calls) / 10

    monkeypatch.setattr(lofcz, "_predict", predict)
    result = lofcz.analyze_audio(Audio(samples, RATE, meta), Path("model.onnx"))

    assert len(calls) == result["evenWindowCount"] == len(result["segments"])
    assert result["segments"] == result["evenWindows"]
    assert result["segmentMean"] == result["score"]
