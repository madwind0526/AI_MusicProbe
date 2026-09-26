from pathlib import Path

import pytest

from probe.file_browser import browse_directory


def test_browse_directory_lists_folders_and_audio_only(tmp_path: Path) -> None:
    (tmp_path / "Album").mkdir()
    (tmp_path / "track.wav").write_bytes(b"audio")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    listing = browse_directory(str(tmp_path))

    assert listing["path"] == str(tmp_path.resolve())
    assert [(item["name"], item["type"]) for item in listing["entries"]] == [
        ("Album", "directory"),
        ("track.wav", "file"),
    ]


def test_browse_directory_rejects_file_path(tmp_path: Path) -> None:
    file_path = tmp_path / "track.wav"
    file_path.write_bytes(b"audio")

    with pytest.raises(ValueError, match="폴더가 아닙니다"):
        browse_directory(str(file_path))
