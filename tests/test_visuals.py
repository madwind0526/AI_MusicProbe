import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from probe import visuals


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + (b"visual" * 32)


def test_concurrent_visual_requests_render_once_and_publish_complete_png(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"audio")
    visual_dir = tmp_path / "visuals"
    calls = []

    monkeypatch.setattr(visuals, "VISUAL_DIR", visual_dir)
    monkeypatch.setattr(visuals.shutil, "which", lambda _name: "ffmpeg")

    def fake_run(command, **_kwargs):
        calls.append(command)
        time.sleep(0.03)
        Path(command[-1]).write_bytes(PNG_BYTES)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(visuals.subprocess, "run", fake_run)

    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda _index: visuals.render_audio_visual(str(audio), "spectrogram"), range(2)))

    assert paths[0] == paths[1]
    assert paths[0].read_bytes() == PNG_BYTES
    assert len(calls) == 1


def test_corrupt_cached_visual_is_regenerated(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"audio")
    visual_dir = tmp_path / "visuals"
    visual_dir.mkdir()
    target = visuals.visual_cache_path(audio.resolve(), "spectrogram", visual_dir)
    target.write_bytes(b"truncated")

    monkeypatch.setattr(visuals, "VISUAL_DIR", visual_dir)
    monkeypatch.setattr(visuals.shutil, "which", lambda _name: "ffmpeg")

    def fake_run(command, **_kwargs):
        Path(command[-1]).write_bytes(PNG_BYTES)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(visuals.subprocess, "run", fake_run)

    assert visuals.render_audio_visual(str(audio), "spectrogram").read_bytes() == PNG_BYTES
