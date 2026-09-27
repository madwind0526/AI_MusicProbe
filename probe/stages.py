"""Stage discovery and ordering.

A "stage" is one render of a track along the production chain. The interesting
question is never about a single file, it is about the difference between two of
them, so a stage set is the unit of analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audioio import is_audio_file
from .config import AUDIO_EXTENSIONS, STAGE_ORDER

# SongYUE2 writes its timbre-transform stages under runs/<id>/stems/. The names
# below are the order the chain actually runs in.
SONGYUE_STEM_MAP = {
    "source.wav": "source_original",
    "source-44k.wav": "source_44k",
    "vocals-original.wav": "vocal_pre_svc",
    "instrumental.wav": "instrumental",
    "vocals.wav": "vocal_post_svc",
}


class StageError(RuntimeError):
    """Raised when a stage set cannot be resolved to audio files."""


@dataclass(frozen=True)
class StageSet:
    name: str
    stages: dict[str, Path]

    def ordered(self) -> list[tuple[str, Path]]:
        return ordered_pairs(self)


def ordered_pairs(stage_set: StageSet) -> list[tuple[str, Path]]:
    """Stage names in chain order: known stages first, then extras alphabetically."""
    known = [s for s in STAGE_ORDER if s in stage_set.stages]
    extra = sorted(s for s in stage_set.stages if s not in STAGE_ORDER)
    return [(name, stage_set.stages[name]) for name in [*known, *extra]]


def from_map(name: str, mapping: dict[str, str | Path]) -> StageSet:
    stages: dict[str, Path] = {}
    missing: list[str] = []
    for stage, raw in mapping.items():
        path = Path(raw).expanduser()
        if not path.is_file():
            missing.append(f"{stage} -> {path}")
            continue
        stages[stage] = path.resolve()
    if missing:
        raise StageError("_stage 파일을 찾을 수 없습니다: " + "; ".join(missing))
    if not stages:
        raise StageError("stage가 비어 있습니다. 최소 1개는 필요합니다.")
    return StageSet(name=name, stages=stages)


def from_directory(path: str | Path, name: str | None = None) -> StageSet:
    directory = Path(path).expanduser()
    if not directory.is_dir():
        raise StageError(f"디렉터리가 아닙니다: {directory}")

    stems = directory / "stems"
    if stems.is_dir():
        stages: dict[str, Path] = {}
        for file in sorted(stems.iterdir()):
            if not is_audio_file(file):
                continue
            stage = SONGYUE_STEM_MAP.get(file.name.lower())
            stages[stage or file.stem] = file.resolve()
        if stages:
            return StageSet(name=name or directory.name, stages=stages)

    stages = {}
    for file in sorted(directory.iterdir()):
        if is_audio_file(file):
            stages[file.stem] = file.resolve()
    if not stages:
        raise StageError(
            f"오디오 파일이 없습니다: {directory} (지원 확장자: {', '.join(AUDIO_EXTENSIONS)})"
        )
    return StageSet(name=name or directory.name, stages=stages)


def load(path: str | Path) -> StageSet:
    """Resolve a stage set from a JSON map file, a SongYUE2 run dir, or a folder."""
    target = Path(path).expanduser()
    if target.is_file() and target.suffix.lower() == ".json":
        import json

        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise StageError(f"stage 맵 JSON은 객체여야 합니다: {target}")
        mapping = payload.get("stages", payload)
        if not isinstance(mapping, dict):
            raise StageError(f"stage 맵 JSON의 'stages'가 객체가 아닙니다: {target}")
        resolved = {k: (v if Path(str(v)).is_absolute() else target.parent / str(v)) for k, v in mapping.items()}
        return from_map(name=payload.get("name", target.stem) if isinstance(payload, dict) else target.stem,
                        mapping={k: Path(str(v)) for k, v in resolved.items()})
    if not target.exists():
        raise StageError(f"경로를 찾을 수 없습니다: {target}")
    return from_directory(target)


__all__ = ["SONGYUE_STEM_MAP", "StageError", "StageSet", "from_directory", "from_map", "load", "ordered_pairs"]
