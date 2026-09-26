import math

import pytest
from pathlib import Path

from probe.file_analysis import _combine, _score, expand_inputs


def test_expand_inputs_returns_supported_files_once(tmp_path: Path) -> None:
    album = tmp_path / "album"
    album.mkdir()
    song = album / "song.wav"
    song.write_bytes(b"placeholder")
    (album / "cover.jpg").write_bytes(b"placeholder")

    result = expand_inputs([album, song])

    assert result == [song.resolve()]


def test_score_requires_detector_corroboration() -> None:
    total, confidence, _conclusion, detail = _score(
        [
            {"name": "sonics", "score": 0.81},
            {"name": "lofcz", "score": 0.0},
        ]
    )

    assert total is not None
    assert total < 1
    assert confidence < 20
    assert detail["inputs"] == {"sonics": 0.81, "lofcz": 0.0}


def test_score_stays_high_when_detectors_agree() -> None:
    total, confidence, _conclusion, _detail = _score(
        [
            {"name": "sonics", "score": 0.88},
            {"name": "lofcz", "score": 1.0},
        ]
    )

    assert total is not None
    assert total > 90
    assert confidence > 70


def test_evaluation_only_detector_is_scored_but_not_combined() -> None:
    total, _confidence, _conclusion, detail = _score(
        [
            {"name": "sonics", "score": 0.9, "includedInTotal": True},
            {"name": "lofcz", "score": 0.8, "includedInTotal": True},
            {"name": "artifactnet", "score": 0.0022, "includedInTotal": False},
        ]
    )

    assert detail["included"] == ["sonics", "lofcz"]
    assert detail["excluded"] == ["artifactnet"]
    assert detail["inputs"]["artifactnet"] == 0.0022
    # The excluded near-zero score no longer drags the total down.
    assert total is not None and total > 80


def test_evaluation_only_total_reports_why_it_failed() -> None:
    total, _confidence, conclusion, _detail = _score(
        [{"name": "artifactnet", "score": 0.0022, "includedInTotal": False}]
    )

    assert total is None
    assert "평가만" in conclusion


def test_arithmetic_mean_lets_a_strong_detector_carry_a_weak_one() -> None:
    results = [
        {"name": "sonics", "score": 0.9, "includedInTotal": True},
        {"name": "lofcz", "score": 0.0, "includedInTotal": True},
    ]

    geometric, _c, _t, _d = _score(results, {"method": "geometric", "weights": {}})
    arithmetic, _c2, _t2, detail = _score(results, {"method": "arithmetic", "weights": {}})

    assert detail["method"] == "detector-arithmetic-mean-v1"
    assert arithmetic is not None and geometric is not None
    assert arithmetic > geometric + 30


def test_weighted_geometric_uses_only_the_relative_weights() -> None:
    results = [
        {"name": "sonics", "score": 0.9, "includedInTotal": True},
        {"name": "lofcz", "score": 0.5, "includedInTotal": True},
    ]

    single, _c, _t, detail = _score(results, {"method": "weightedGeometric", "weights": {"sonics": 0, "lofcz": 1}})

    assert detail["weights"] == {"lofcz": 1.0}
    assert single == 50.0


def test_all_zero_weights_do_not_silently_change_the_combination_method() -> None:
    values = [0.2, 0.6]

    with pytest.raises(ValueError, match="가중치"):
        _combine(values, ["a", "b"], "weightedGeometric", {"a": 0, "b": 0})


def test_zero_weight_detector_is_excluded_from_score_and_confidence() -> None:
    results = [
        {"name": "sonics", "score": 0.9, "includedInTotal": True},
        {"name": "lofcz", "score": 0.0, "includedInTotal": True},
    ]

    total, confidence, _conclusion, detail = _score(
        results, {"method": "weightedGeometric", "weights": {"sonics": 1, "lofcz": 0}}
    )

    assert total == 90.0
    assert confidence == 80.0
    assert detail["included"] == ["sonics"]
    assert detail["excluded"] == ["lofcz"]


def test_median_combination_ignores_a_single_outlier() -> None:
    results = [
        {"name": "sonics", "score": 0.8, "includedInTotal": True},
        {"name": "lofcz", "score": 0.8, "includedInTotal": True},
        {"name": "artifactnet", "score": 0.01, "includedInTotal": True},
    ]

    median, _c, _t, detail = _score(results, {"method": "median", "weights": {}})

    assert detail["method"] == "detector-median-v1"
    assert median == 80.0


def test_non_finite_detector_score_is_ignored() -> None:
    total, _confidence, _conclusion, detail = _score(
        [
            {"name": "sonics", "score": 0.8, "includedInTotal": True},
            {"name": "lofcz", "score": math.nan, "includedInTotal": True},
        ]
    )

    # A NaN used to clip to 1.0 and look like a saturated detector.
    assert detail["inputs"] == {"sonics": 0.8}
    assert total == 80.0
