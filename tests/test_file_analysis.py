from pathlib import Path

from probe.file_analysis import _score, expand_inputs


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
