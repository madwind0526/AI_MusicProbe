"""Stage comparison and chain/confound decomposition.

The single most important thing this module refuses to do is present a raw
"AI-ness dropped from 0.82 to 0.31" claim. What it reports instead is how much
of the observed movement a human control track shows when pushed through the
same chain, because most of that movement is the chain, not the music.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import dsp
from .audioio import AudioToolError, load as load_audio
from .config import PEAK_MAX_COUNT, STANDARD_RATE_HZ
from .detectors import describe as describe_detectors
from .stages import StageSet, ordered_pairs

# Digital-silence ceilings left by a resample or a lossy codec.
KNOWN_CEILINGS_HZ = (8000.0, 11025.0, 12000.0, 16000.0, 22050.0, 24000.0)
CEILING_TOLERANCE = 0.01

# Two peaks count as the same artifact when they sit within this fraction of
# Nyquist of each other.
PEAK_MATCH_TOLERANCE = 0.01

# Above this ratio the observed movement is better explained by the chain than
# by the content, and the metric should not be read as a change in "AI-ness".
CHAIN_DOMINANT_RATIO = 0.8
CHAIN_MIN_DELTA = 0.5

# Paths excluded from the flat numeric delta table. The spectrum curve is chart
# data, not a metric: 512 array entries per stage would drown everything else.
EXCLUDED_PREFIXES = ("meta.path", "spectral.curve")


def flatten_numbers(node: Any, prefix: str = "") -> dict[str, float]:
    """Flatten a profile into dotted numeric paths, dropping nulls and chart data."""
    out: dict[str, float] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if any(path == p or path.startswith(f"{p}.") for p in EXCLUDED_PREFIXES):
                continue
            out.update(flatten_numbers(value, path))
    elif isinstance(node, bool):
        pass
    elif isinstance(node, (int, float)):
        out[prefix] = float(node)
    return out


def _profile(path: Path) -> dict:
    return dsp.analyze(load_audio(path))


def _order(stage_set: StageSet) -> list[tuple[str, Path]]:
    return ordered_pairs(stage_set)


def analyze(stage_set: StageSet, control_set: StageSet | None = None) -> dict:
    stages = _order(stage_set)
    profiles = [{"stage": name, "order": index, "file": str(path), "profile": _profile(path)}
                for index, (name, path) in enumerate(stages)]

    flat = [flatten_numbers(item["profile"]) for item in profiles]
    metric_paths = sorted({key for row in flat for key in row})

    deltas = {}
    for path in metric_paths:
        series = [row.get(path) for row in flat]
        if len(series) < 2 or series[0] is None or series[-1] is None:
            continue
        first, last = series[0], series[-1]
        deltas[path] = {
            "series": series,
            "first": first,
            "last": last,
            "change": round(last - first, 4),
        }

    control = None
    decomposition = {}
    if control_set is not None:
        control_stages = _order(control_set)
        control_profiles = [{"stage": name, "order": index, "file": str(path), "profile": _profile(path)}
                            for index, (name, path) in enumerate(control_stages)]
        control_flat = [flatten_numbers(item["profile"]) for item in control_profiles]
        control_deltas = {}
        for path in metric_paths:
            series = [row.get(path) for row in control_flat]
            if len(series) < 2 or series[0] is None or series[-1] is None:
                continue
            control_deltas[path] = {"series": series, "change": round(series[-1] - series[0], 4)}
        control = {
            "name": control_set.name,
            "stages": control_profiles,
            "deltas": control_deltas,
        }
        decomposition = _decompose(deltas, control_deltas)

    return {
        "tool": "ai-music-probe",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "detectors": describe_detectors(),
        "target": {
            "name": stage_set.name,
            "stages": profiles,
            "deltas": deltas,
            "peakDiff": _peak_diff(profiles),
        },
        "control": control,
        "chainDecomposition": decomposition,
        "flags": _flags(profiles, control, stage_set),
    }


def _decompose(deltas: dict, control_deltas: dict) -> dict:
    out: dict[str, dict] = {}
    for path, target in deltas.items():
        control = control_deltas.get(path)
        if control is None:
            continue
        target_change = float(target["change"])
        control_change = float(control["change"])
        if abs(target_change) < CHAIN_MIN_DELTA:
            continue
        floor_ratio = abs(control_change) / abs(target_change)
        signed = control_change / target_change if target_change else 0.0
        out[path] = {
            "targetChange": round(target_change, 4),
            "controlChange": round(control_change, 4),
            "chainFractionSigned": round(signed, 3),
            "chainFloorRatio": round(floor_ratio, 3),
            "verdict": _verdict(floor_ratio, signed),
        }
    out["_note"] = {
        "chainFloorRatio": "대조군 변화 / 대상 변화 절댓값. 1.0에 가까우면 관측된 변화가 체인 부작용으로 설명된다.",
        "chainFractionSigned": "부호 포함 비율. 1.0이면 체인이 같은 방향으로 움직였다는 뜻.",
    }
    return out


def _verdict(floor_ratio: float, signed: float) -> str:
    if floor_ratio >= CHAIN_DOMINANT_RATIO and signed > 0:
        return "chain-dominant"
    if floor_ratio >= CHAIN_DOMINANT_RATIO:
        return "chain-dominant-inverse"
    if floor_ratio <= 0.2:
        return "content-specific"
    return "mixed"


def _peak_diff(profiles: list[dict]) -> dict:
    """Which artifact peak positions appear or disappear between first and last stage."""
    if len(profiles) < 2:
        return {"added": [], "removed": [], "note": "stage가 2개 미만이라 peak 변화 없음."}
    first = profiles[0]["profile"].get("artifactFingerprint") or []
    last = profiles[-1]["profile"].get("artifactFingerprint") or []
    if not first or not last:
        return {"added": [], "removed": [], "note": "첫 또는 마지막 stage에 peak가 잡히지 않음."}

    nyquist = (profiles[-1]["profile"]["meta"]["sampleRate"] or 44100) / 2.0
    tolerance = nyquist * PEAK_MATCH_TOLERANCE
    first_hz = [float(p["hz"]) for p in first]
    last_hz = [float(p["hz"]) for p in last]

    def unmatched(source: list[float], reference: list[float]) -> list[float]:
        return [round(hz, 1) for hz in source if all(abs(hz - other) > tolerance for other in reference)]

    return {
        "added": unmatched(last_hz, first_hz),
        "removed": unmatched(first_hz, last_hz),
        "toleranceHz": round(tolerance, 1),
        "note": "peak 위치는 아키텍처에 의존한다. 위치 이동은 보코더/리샘플러가 바뀌었다는 신호로 읽는다.",
    }


def _flags(profiles: list[dict], control: dict | None, stage_set: StageSet) -> list[dict]:
    flags: list[dict] = []
    metas = [item["profile"]["meta"] for item in profiles]

    if len(profiles) < 2:
        flags.append({
            "level": "warn", "code": "single-stage",
            "message": f"stage가 {len(profiles)}개뿐이라 변화량을 계산할 수 없습니다.",
        })

    rates = {meta["sampleRate"] for meta in metas}
    if len(rates) > 1:
        flags.append({
            "level": "error", "code": "rate-mismatch",
            "message": f"stage마다 샘플레이트가 다릅니다: {sorted(rates)}. 비교 자체가 성립하지 않습니다.",
        })
    for meta in metas:
        if meta["sampleRate"] and meta["sampleRate"] != STANDARD_RATE_HZ:
            flags.append({
                "level": "warn", "code": "rate-nonstandard",
                "message": f"{Path(meta['path']).name} 샘플레이트 {meta['sampleRate']}Hz (기준 {STANDARD_RATE_HZ}Hz).",
            })
        if meta["lossy"]:
            flags.append({
                "level": "error", "code": "lossy-codec",
                "message": f"{Path(meta['path']).name} 코덱 {meta['codec']}은(는) 손실 압축입니다. AI 탐지 점수에 직접 잡힙니다.",
            })

    for item in profiles:
        null_hz = (item["profile"].get("spectral") or {}).get("digitalNullHz")
        rate = item["profile"]["meta"].get("sampleRate") or 0
        if not null_hz or not rate:
            continue
        nyquist = rate / 2.0
        # A digital null sitting exactly at Nyquist is just the file's own band
        # limit, which every native-rate file has. Only a null *below* Nyquist
        # means something was cut or resampled away.
        if null_hz >= nyquist * 0.995:
            continue
        for ceiling in KNOWN_CEILINGS_HZ:
            if abs(null_hz - ceiling) <= ceiling * CEILING_TOLERANCE:
                flags.append({
                    "level": "warn", "code": "resample-ceiling",
                    "message": f"{item['stage']}: {null_hz:.0f}Hz에서 디지털 무음. {ceiling:.0f}Hz로 리샘플 또는 컷된 흔적.",
                })
                break
        else:
            flags.append({
                "level": "warn", "code": "sub-nyquist-cut",
                "message": f"{item['stage']}: {nyquist:.0f}Hz(Nyquist)보다 낮은 {null_hz:.0f}Hz에서 디지털 무음. "
                           f"리샘플·코덱·보코더 중 하나가 대역폭을 잘랐습니다.",
            })

    for item in profiles:
        peak_count = len(item["profile"].get("artifactFingerprint") or [])
        if peak_count >= PEAK_MAX_COUNT:
            flags.append({
                "level": "warn", "code": "peak-list-saturated",
                "message": f"{item['stage']}: peak가 {PEAK_MAX_COUNT}개로 잘렸습니다. "
                           f"이 단계의 peak 위치 비교(추가/사라짐)는 신뢰하지 마세요.",
            })

    durations = [meta["durationS"] for meta in metas if meta["durationS"]]
    if len(durations) >= 2 and durations:
        spread = (max(durations) - min(durations)) / max(durations)
        if spread > 0.01:
            flags.append({
                "level": "warn", "code": "duration-mismatch",
                "message": f"stage 간 길이 차이 {spread * 100:.1f}%. 타임스트레치가 섞였을 수 있습니다.",
            })

    if control is None:
        flags.append({
            "level": "warn", "code": "no-control",
            "message": "대조군(인간 음원)이 없습니다. 체인 부작용과 콘텐츠 변화를 구분할 수 없습니다.",
        })
    return flags


def _chain_dominant_flags(report: dict) -> list[dict]:
    """Separate pass: turn dominant ratios into readable flags."""
    out: list[dict] = []
    for path, entry in (report.get("chainDecomposition") or {}).items():
        if path.startswith("_") or not isinstance(entry, dict):
            continue
        if entry.get("verdict") in ("chain-dominant", "chain-dominant-inverse"):
            out.append({
                "level": "info", "code": "chain-dominant",
                "message": f"{path}: 대상 변화 {entry['targetChange']} 중 대조군 변화 {entry['controlChange']} (비율 {entry['chainFloorRatio']}). 체인 부작용으로 보입니다.",
            })
    return out


def with_chain_flags(report: dict) -> dict:
    report["flags"].extend(_chain_dominant_flags(report))
    return report


def to_json(report: dict, indent: int = 2) -> str:
    return json.dumps(report, ensure_ascii=False, indent=indent)


def save(report: dict, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    candidate = out
    index = 0
    while True:
        try:
            with candidate.open("x", encoding="utf-8") as stream:
                stream.write(to_json(report))
            return candidate
        except FileExistsError:
            index += 1
            candidate = out.with_name(f"{out.stem} ({index}){out.suffix}")


__all__ = ["analyze", "flatten_numbers", "save", "to_json", "with_chain_flags"]
