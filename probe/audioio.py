"""ffprobe/ffmpeg wrappers.

Everything is decoded at the file's native sample rate and channel count. No
resampling happens here on purpose: resampling rewrites the spectral ceiling and
would erase the evidence this tool exists to collect.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import AUDIO_EXTENSIONS

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")


class AudioToolError(RuntimeError):
    """Raised when ffmpeg/ffprobe are missing or an audio file cannot be read."""


def require_tools() -> None:
    missing = [name for name, path in (("ffmpeg", _FFMPEG), ("ffprobe", _FFPROBE)) if not path]
    if missing:
        raise AudioToolError(f"필수 외부 도구가 없습니다: {', '.join(missing)}. PATH에 등록해 주세요.")


@dataclass(frozen=True)
class AudioMeta:
    path: Path
    codec: str
    sample_rate: int
    channels: int
    duration_s: float
    bits_per_sample: int | None
    lossy: bool

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "codec": self.codec,
            "sampleRate": self.sample_rate,
            "channels": self.channels,
            "durationS": round(self.duration_s, 3),
            "bitsPerSample": self.bits_per_sample,
            "lossy": self.lossy,
        }


LOSSLESS_CODECS = {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "flac", "alac", "wavpack", "ape"}


def probe(path: str | Path) -> AudioMeta:
    require_tools()
    file_path = Path(path)
    if not file_path.is_file():
        raise AudioToolError(f"파일을 찾을 수 없습니다: {file_path}")

    result = subprocess.run(
        [
            _FFPROBE, "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise AudioToolError(f"ffprobe 실패 ({file_path.name}): {detail[-1] if detail else '알 수 없는 오류'}")

    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    if not streams:
        raise AudioToolError(f"오디오 스트림이 없습니다: {file_path.name}")

    stream = streams[0]
    fmt = payload.get("format") or {}
    codec = str(stream.get("codec_name") or "unknown")
    bits = stream.get("bits_per_raw_sample") or stream.get("bits_per_sample")
    return AudioMeta(
        path=file_path,
        codec=codec,
        sample_rate=int(stream.get("sample_rate") or 0),
        channels=int(stream.get("channels") or 0),
        duration_s=float(fmt.get("duration") or 0.0),
        bits_per_sample=int(bits) if bits else None,
        lossy=codec not in LOSSLESS_CODECS,
    )


@dataclass(frozen=True)
class Audio:
    """Decoded float32 audio. Shape is (frames, channels)."""

    samples: np.ndarray
    sample_rate: int
    meta: AudioMeta

    @property
    def duration_s(self) -> float:
        return self.samples.shape[0] / float(self.sample_rate)

    def mono(self) -> np.ndarray:
        return self.samples.mean(axis=1)


def load(path: str | Path) -> Audio:
    require_tools()
    file_path = Path(path)
    meta = probe(file_path)
    if meta.sample_rate <= 0 or meta.channels <= 0:
        raise AudioToolError(f"샘플레이트/채널 정보를 읽을 수 없습니다: {file_path.name}")

    result = subprocess.run(
        [
            _FFMPEG, "-v", "error", "-nostdin", "-i", str(file_path),
            "-f", "f32le", "-acodec", "pcm_f32le",
            "-ar", str(meta.sample_rate), "-ac", str(meta.channels),
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        detail = (result.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise AudioToolError(f"디코딩 실패 ({file_path.name}): {detail[-1] if detail else '알 수 없는 오류'}")

    flat = np.frombuffer(result.stdout, dtype="<f4")
    if flat.size % meta.channels:
        raise AudioToolError(f"디코딩 결과가 채널 수로 나누어떨어지지 않습니다: {file_path.name}")
    samples = np.ascontiguousarray(flat.reshape(-1, meta.channels), dtype=np.float32)
    if not np.all(np.isfinite(samples)):
        # ffmpeg can emit NaN/Inf for damaged files; drop them so downstream
        # percentiles stay defined instead of poisoning every metric.
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
    return Audio(samples=samples, sample_rate=meta.sample_rate, meta=meta)


def is_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
