"""Cached waveform and spectrogram rendering through FFmpeg."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .audioio import is_audio_file, load
from .config import SCRATCH_DIR

VISUAL_DIR = SCRATCH_DIR / "visuals"


def visual_cache_path(path: Path, kind: str, visual_dir: Path = VISUAL_DIR) -> Path:
    identity = f"{path}|{path.stat().st_mtime_ns}|{kind}".encode("utf-8")
    return visual_dir / f"{hashlib.sha256(identity).hexdigest()}.png"


def waveform_peaks(raw_path: str, count: int = 180) -> dict:
    """Return a compact loudness envelope for a SongYUE-style bar waveform.

    Each bar is the RMS of its slice rather than the slice's absolute maximum.
    A per-slice max reports the loudest instant in the slice, so on a dense,
    heavily mastered human track almost every slice lands near full scale; after
    normalising by the global max the shape is then a solid slab that reads as
    the waveform overflowing its box. RMS keeps the envelope's dynamics, and the
    result is still scaled so the tallest bar fills the view exactly.
    """
    path = validate_audio_path(raw_path)
    audio = load(path)
    mono = audio.mono()
    if not len(mono):
        return {"peaks": [], "duration": 0.0, "sampleRate": audio.sample_rate, "metric": "rms"}
    count = max(40, min(400, int(count)))
    edges = np.linspace(0, len(mono), count + 1, dtype=int)
    envelope = []
    for index in range(count):
        chunk = mono[edges[index]:edges[index + 1]]
        envelope.append(float(np.sqrt(np.mean(np.square(chunk)) if len(chunk) else 0.0)))
    scale = max(envelope) or 1.0
    return {
        "peaks": [round(value / scale, 4) for value in envelope],
        "duration": round(audio.duration_s, 3),
        "sampleRate": audio.sample_rate,
        "metric": "rms",
    }


def validate_audio_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve(strict=True)
    if not path.is_file() or not is_audio_file(path):
        raise ValueError("지원하는 음원 파일이 아닙니다.")
    return path


def render_audio_visual(raw_path: str, kind: str) -> Path:
    path = validate_audio_path(raw_path)
    if kind not in {"waveform", "spectrogram"}:
        raise ValueError("지원하지 않는 시각화 형식입니다.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("FFmpeg를 찾지 못해 시각화를 만들 수 없습니다.")

    target = visual_cache_path(path, kind)
    if target.is_file():
        return target
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    filter_value = (
        "showwavespic=s=1200x180:colors=0xb996ff:split_channels=0"
        if kind == "waveform"
        else "showspectrumpic=s=1200x300:legend=disabled:scale=log:color=rainbow"
    )
    process = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-lavfi", filter_value, "-frames:v", "1", "-y", str(target)],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process.returncode != 0 or not target.is_file():
        raise ValueError("오디오 시각화를 만들지 못했습니다.")
    return target
