"""Detector analysis options: schema, locked model inputs, persistence.

Two separate groups of values live in every detector:

* `locked` — preprocessing that the checkpoint was trained with. Sample rate,
  FFT size, band edges, and the fixed input window length. Changing any of them
  changes what the model is looking at, so they are reported and never edited.
* `options` — segment selection, song-level aggregation, decision threshold,
  and Total participation. Each one declares whether it moves the raw score,
  only the verdict, or the Total combination.

Storage is a separate `detector-options.json` file so the general WebUI
settings screen stays untouched. Values are re-read on every run, so a save
applies to the next analysis without a server restart.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPTIONS_PATH = ROOT / "detector-options.json"

#: The control moves the raw detector score that feeds the ensemble.
EFFECT_SCORE = "score"
#: The control only moves the AI/human verdict label for one detector.
EFFECT_VERDICT = "verdict"
#: The control only moves how detector scores are combined into the Total.
EFFECT_TOTAL = "total"

EFFECT_LABELS = {
    EFFECT_SCORE: "원점수에 반영",
    EFFECT_VERDICT: "판정에만 사용",
    EFFECT_TOTAL: "Total 결합에 사용",
}

ENSEMBLE_METHODS: tuple[tuple[str, str], ...] = (
    ("robustMean", "이상치 제외 평균 (기본값)"),
    ("weightedGeometric", "가중 기하평균"),
    ("geometric", "기하평균"),
    ("arithmetic", "산술평균"),
    ("median", "중앙값"),
)

ENSEMBLE_METHOD_LABELS = {
    "geometric": "활성 탐지기가 서로 동의할 때만 점수가 올라갑니다. 한 모델의 낮은 점수가 전체를 크게 끌어내립니다. "
                 "계산: 모든 점수를 곱한 뒤 탐지기 개수만큼 거듭제곱근을 취합니다. "
                 "예: 0.85, 0.60, 0.90 → (0.85×0.60×0.90)^(1/3) ≈ 77.1%.",
    "arithmetic": "모든 탐지기의 원점수를 단순히 더합니다. 낮은 점수를 다른 모델이 상쇄합니다. "
                  "계산: 점수를 모두 더해 탐지기 개수로 나눕니다. "
                  "예: 0.85, 0.60, 0.90 → (0.85+0.60+0.90)/3 ≈ 78.3%.",
    "median": "가운데 값만 봅니다. 탐지기 수가 많을 때 극단값에 덜 흔들립니다. "
              "계산: 점수를 크기순으로 줄 세운 뒤 가운데 값 하나만 씁니다(짝수 개면 가운데 두 값의 평균). "
              "예: 0.85, 0.60, 0.90 → 크기순 0.60, 0.85, 0.90 중 가운데 → 85.0%.",
    "weightedGeometric": "탐지기별 가중치를 기하평균에 곱합니다. 가중치 0은 Total에서 빠집니다. "
                         "계산: 각 점수에 그 탐지기 가중치 비중만큼 지수를 줘서 곱합니다(가중치가 클수록 그 탐지기가 더 크게 반영됨). "
                         "예: 0.85, 0.60, 0.90에 가중치 2:1:1을 주면(0.85를 더 신뢰) → 약 79.0%(가중치 없는 기하평균 77.1%보다 0.85 쪽으로 더 쏠림).",
    "robustMean": "중앙값 기준으로 크게 벗어난(이상치) 탐지기를 걸러내고, 남은 탐지기의 점수만 평균합니다. 탐지기가 2개 이하면 모두 그대로 평균합니다. "
                  "계산: 중앙값과 각 점수의 차이를 중앙값절대편차(MAD)로 나눈 값(수정 z-점수)이 3.5보다 크면 그 탐지기를 빼고 나머지만 평균합니다. "
                  "예: 0.854, 0.996, 0.0 → 중앙값 0.854, MAD 0.142, 0.0의 z ≈ -4.06으로 이상치 판정되어 제외 → 남은 0.854, 0.996만 평균 → 92.5%.",
}

MIN_THRESHOLD = 0.05
MAX_THRESHOLD = 0.95


def _choice(key: str, label: str, unit: str, default: Any, choices: list[Any], effect: str, hint: str,
            choice_labels: list[str] | None = None) -> dict[str, Any]:
    labels = choice_labels or [str(value) for value in choices]
    return {"key": key, "type": "choice", "label": label, "unit": unit, "default": default,
            "choices": [{"value": value, "label": text} for value, text in zip(choices, labels, strict=True)],
            "effect": effect, "hint": hint}


def _number(key: str, label: str, unit: str, default: float, effect: str, hint: str,
            minimum: float = MIN_THRESHOLD, maximum: float = MAX_THRESHOLD) -> dict[str, Any]:
    return {"key": key, "type": "number", "label": label, "unit": unit, "default": default,
            "min": minimum, "max": maximum, "step": 0.01, "effect": effect, "hint": hint}


_INCLUDED_OPTION = {
    "key": "includedInTotal",
    "type": "toggle",
    "label": "Total 반영",
    "unit": "",
    "default": True,
    "effect": EFFECT_TOTAL,
    "hint": "켜면 원점수를 총점 결합에 사용하고, 끄면 점수는 계산하되 총점에는 넣지 않습니다.",
}

#: Detectors without a trained weight still get a Total toggle so the schema is
#: complete; the value is inert until a model is wired in.
DETECTOR_SCHEMA: dict[str, dict[str, Any]] = {
    "sonics": {
        "label": "SONICS / SpecTTTra gamma 5s",
        "locked": [
            {"label": "입력 샘플레이트", "value": "16,000 Hz"},
            {"label": "구간 길이", "value": "5.0초"},
            {"label": "구간 정규화", "value": "구간별 표준편차 1.0"},
            {"label": "모델", "value": "awsaf49/sonics-spectttra-gamma-5s"},
        ],
        "lockedNote": "이 값들은 학습 입력과 연결되어 있습니다. 바꾸면 다른 길이의 학습 데이터로 평가하게 되므로 수정할 수 없습니다.",
        "options": [
            _choice("maxWindows", "최대 구간 수", "개", 24, [8, 16, 24], EFFECT_SCORE,
                    "곡 전체에서 뽑을 5초 구간의 최대 개수입니다. 적게 잡으면 곡 앞부분에 치우칩니다.",
                    ["8개", "16개", "24개 (기본)"]),
            _choice("hopSeconds", "구간 간격", "초", 2.5, [2.5, 5.0], EFFECT_SCORE,
                    "구간을 옮기는 간격입니다. 5초면 겹치지 않게 반씩만 봅니다.",
                    ["2.5초 (기본)", "5초"]),
            _choice("aggregation", "구간 집계", "", "median", ["topk", "mean", "median"], EFFECT_SCORE,
                    "topk는 강한 구간 K개 평균, mean은 전체 평균, median은 중앙값입니다.",
                    ["상위 K개 평균", "전체 평균", "중앙값 (기본)"]),
            _choice("topK", "Top-K 개수", "개", 3, [1, 3, 5], EFFECT_SCORE,
                    "구간 집계가 상위 K개 평균일 때만 사용됩니다. 1개는 가장 강한 한 구간만 봅니다.",
                    ["1개", "3개 (기본)", "5개"]),
            _number("threshold", "판정 임계값", "", 0.5, EFFECT_VERDICT,
                    "이 값 이상이면 AI 우세로 표시합니다. Total 계산에는 사용하지 않습니다."),
        ],
    },
    "lofcz": {
        "label": "lofcz vocoder fakeprint",
        "locked": [
            {"label": "입력 샘플레이트", "value": "16,000 Hz"},
            {"label": "FFT 크기 / 간격", "value": "8,192 / 4,096"},
            {"label": "분석 대역", "value": "1,000–8,000 Hz"},
            {"label": "lower-envelope 크기", "value": "10"},
            {"label": "dB 범위", "value": "−45 ~ +5 dB"},
        ],
        "lockedNote": "이 값들은 보코더 재구성 특징의 정의입니다. 수정하면 fakeprint 계산 자체가 달라집니다.",
        "options": [
            _choice("maxDurationS", "최대 분석 길이", "초", 300, [60, 180, 300], EFFECT_SCORE,
                    "한 번에 판정할 오디오 길이입니다. 짧게 잡으면 곡 뒷부분을 보지 못합니다.",
                    ["60초", "180초", "300초 (기본)"]),
            _choice("analysisPosition", "분석 위치", "", "start", ["start", "even"], EFFECT_SCORE,
                    "곡 앞부분은 한 번에 판정하고, 곡 전체 고르기는 같은 길이로 나눠 고르게 판정합니다.",
                    ["곡 앞부분 (기본)", "곡 전체 고르게"]),
            _choice("aggregation", "구간 집계", "", "mean", ["mean", "median"], EFFECT_SCORE,
                    "곡 앞부분 모드에서는 한 구간만 사용하므로 이 값이 결과를 바꾸지 않습니다. 곡 전체 고르기에서는 평균 또는 중앙값으로 합칩니다.",
                    ["구간 평균 (기본)", "구간 중앙값"]),
            _number("threshold", "판정 임계값", "", 0.5, EFFECT_VERDICT,
                    "이 값 이상이면 AI 우세로 표시합니다. Total 계산에는 사용하지 않습니다."),
        ],
    },
    "artifactnet": {
        "label": "ArtifactNet v9.4",
        "locked": [
            {"label": "입력 샘플레이트", "value": "44,100 Hz"},
            {"label": "구간 길이", "value": "4.0초"},
            {"label": "모델 형태", "value": "STFT→sigmoid 단일 ONNX (내부 옵션 없음)"},
        ],
        "lockedNote": "공개 모델 카드 규격입니다. 내부 네트워크나 fine-tuning 설정은 열 수 없습니다.",
        "options": [
            _choice("segmentCount", "구간 수", "개", 11, [5, 7, 11], EFFECT_SCORE,
                    "곡에서 4초 구간을 몇 개 뽑을지 정합니다. 공식 값은 7개이며 현재 기본값은 비교 실험에서 선택한 11개입니다.",
                    ["5개", "7개 (공식)", "11개 (기본)"]),
            _choice("segmentSelection", "구간 선택", "", "even", ["even", "start"], EFFECT_SCORE,
                    "곡 전체 고르기는 곡 전체에 고르게, 처음부터는 앞에서부터 차례대로 뽑습니다.",
                    ["곡 전체에 고르게 (공식)", "처음부터"]),
            _choice("aggregation", "구간 집계", "", "top3", ["median", "mean", "top3", "max"], EFFECT_SCORE,
                    "공식 값은 중앙값이며 현재 기본값은 11구간 비교에서 단일 이상치 영향을 줄인 상위 3개 평균입니다.",
                    ["중앙값 (공식)", "평균", "상위 3개 평균 (기본)", "최댓값"]),
            _choice("minValidSegments", "최소 유효 구간", "개", 4, [3, 4], EFFECT_SCORE,
                    "이 개수보다 유효 점수가 적으면 ArtifactNet이 오류로 처리되어 총점에서 빠집니다. 곡이 짧아 구간 자체가 부족할 때는 기준이 구간 수로 자동 낮아집니다.",
                    ["3개", "4개 (공식)"]),
            _number("threshold", "판정 임계값", "", 0.5, EFFECT_VERDICT,
                    "이 값 이상이면 AI 우세로 표시합니다. Total 계산에는 사용하지 않습니다."),
            {
                "key": "levelNormalize",
                "type": "toggle",
                "label": "입력 음량 정규화 (실험)",
                "unit": "",
                "default": False,
                "effect": EFFECT_SCORE,
                "hint": "켜면 구간 RMS를 맞춰 NaN을 줄일 수 있지만 공식 v9.4 입력과 달라집니다. 기본값은 끄기입니다.",
            },
        ],
    },
    "attribution": {
        "label": "생성기 어트리뷰션 헤드",
        "locked": [
            {"label": "상태", "value": "미구현"},
        ],
        "lockedNote": "학습 코퍼스와 체크포인트가 준비되면 이 자리에 설정이 추가됩니다.",
        "options": [],
    },
}

#: ArtifactNet is included in the selected experimental default so every new
#: installation uses the same three-detector protocol as the current project.
#: Its provisional direction must still be validated on a wider paired corpus.
DEFAULT_INCLUDED = {
    "sonics": True,
    "lofcz": True,
    "artifactnet": True,
    "attribution": False,
}

IMPLEMENTED_DETECTORS = {"sonics", "lofcz", "artifactnet"}

DEFAULT_ENSEMBLE: dict[str, Any] = {"method": "robustMean", "weights": {}}


def _default_detector_values(name: str) -> dict[str, Any]:
    spec = DETECTOR_SCHEMA[name]
    values: dict[str, Any] = {"includedInTotal": DEFAULT_INCLUDED[name]}
    for option in spec["options"]:
        values[option["key"]] = deepcopy(option["default"])
    return values


def default_options() -> dict[str, Any]:
    return {name: _default_detector_values(name) for name in DETECTOR_SCHEMA}


def _clamp_number(value: Any, option: dict[str, Any], fallback: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if number != number:  # NaN
        return float(fallback)
    return round(min(float(option["max"]), max(float(option["min"]), number)), 4)


def _coerce_choice(value: Any, option: dict[str, Any], fallback: Any) -> Any:
    for candidate in option["choices"]:
        allowed = candidate["value"]
        if isinstance(allowed, bool):
            if value is allowed:
                return allowed
        elif isinstance(allowed, (int, float)):
            try:
                if float(value) == float(allowed):
                    return allowed
            except (TypeError, ValueError):
                return fallback
        elif value == allowed:
            return allowed
    return fallback


def _normalize_detector(name: str, raw: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = DETECTOR_SCHEMA[name]
    result = dict(fallback) if isinstance(fallback, dict) else _default_detector_values(name)
    if not isinstance(raw, dict):
        return result
    if raw.get("includedInTotal") is not None:
        result["includedInTotal"] = bool(raw["includedInTotal"])
    for option in spec["options"]:
        value = raw.get(option["key"])
        if value is None:
            continue
        if option["type"] == "choice":
            result[option["key"]] = _coerce_choice(value, option, result.get(option["key"], option["default"]))
        elif option["type"] == "number":
            result[option["key"]] = _clamp_number(value, option, result.get(option["key"], option["default"]))
        elif option["type"] == "toggle":
            result[option["key"]] = bool(value)
    return result


def _normalize_weights(raw: Any) -> dict[str, float]:
    weights: dict[str, float] = {}
    if not isinstance(raw, dict):
        return weights
    for name in DETECTOR_SCHEMA:
        if name not in raw:
            continue
        try:
            value = float(raw[name])
        except (TypeError, ValueError):
            continue
        if value != value:  # NaN
            continue
        weights[name] = round(min(10.0, max(0.0, value)), 3)
    return weights


def normalize(data: Any) -> dict[str, Any]:
    """Clamp and complete any user payload, filling in schema defaults."""
    source = data if isinstance(data, dict) else {}
    detectors_raw = source.get("detectors")
    detectors_raw = detectors_raw if isinstance(detectors_raw, dict) else {}
    ensemble_raw = source.get("ensemble")
    ensemble_raw = ensemble_raw if isinstance(ensemble_raw, dict) else {}

    method = ensemble_raw.get("method")
    valid_methods = [name for name, _ in ENSEMBLE_METHODS]
    if method not in valid_methods:
        method = DEFAULT_ENSEMBLE["method"]

    return {
        "detectors": {name: _normalize_detector(name, detectors_raw.get(name)) for name in DETECTOR_SCHEMA},
        "ensemble": {"method": method, "weights": _normalize_weights(ensemble_raw.get("weights"))},
    }


def merge(current_data: Any, patch: Any) -> dict[str, Any]:
    """Merge a partial API payload without resetting unrelated saved values."""
    result = normalize(current_data)
    source = patch if isinstance(patch, dict) else {}
    detector_patch = source.get("detectors")
    if isinstance(detector_patch, dict):
        for name, values in detector_patch.items():
            if name not in result["detectors"] or not isinstance(values, dict):
                continue
            result["detectors"][name] = _normalize_detector(name, values, result["detectors"][name])
    ensemble_patch = source.get("ensemble")
    if isinstance(ensemble_patch, dict):
        method = ensemble_patch.get("method")
        valid_methods = {name for name, _label in ENSEMBLE_METHODS}
        if method in valid_methods:
            result["ensemble"]["method"] = method
        weight_patch = ensemble_patch.get("weights")
        if isinstance(weight_patch, dict):
            merged_weights = dict(result["ensemble"]["weights"])
            merged_weights.update(_normalize_weights(weight_patch))
            result["ensemble"]["weights"] = merged_weights
    return result


def load() -> dict[str, Any]:
    if not OPTIONS_PATH.is_file():
        return normalize(None)
    try:
        return normalize(json.loads(OPTIONS_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return normalize(None)


def save(data: Any) -> dict[str, Any]:
    settings = normalize(data)
    if settings["ensemble"]["method"] == "weightedGeometric":
        weights = settings["ensemble"]["weights"]
        included = [
            name for name, values in settings["detectors"].items()
            if name in IMPLEMENTED_DETECTORS and values.get("includedInTotal", True)
        ]
        if included and not any(float(weights.get(name, 1.0)) > 0 for name in included):
            raise ValueError("가중 기하평균은 Total에 반영할 탐지기 중 하나 이상의 가중치가 0보다 커야 합니다.")
    temporary = OPTIONS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OPTIONS_PATH)
    _invalidate()
    return settings


def _invalidate() -> None:
    global _CACHE
    _CACHE = None


_CACHE: tuple[float, dict[str, Any]] | None = None


def current() -> dict[str, Any]:
    """Read the live settings, reloading only when the file actually changed."""
    global _CACHE
    try:
        stamp = OPTIONS_PATH.stat().st_mtime
    except OSError:
        stamp = -1.0
    if _CACHE is None or _CACHE[0] != stamp:
        _CACHE = (stamp, load())
    return _CACHE[1]


def for_detector(name: str) -> dict[str, Any]:
    detectors = current()["detectors"]
    return detectors.get(name) or _default_detector_values(name)


def included_in_total(name: str) -> bool:
    return bool(for_detector(name).get("includedInTotal", True))


def describe() -> dict[str, Any]:
    """Full schema plus the values in effect, ready for the WebUI."""
    settings = current()
    detectors = []
    for name, spec in DETECTOR_SCHEMA.items():
        detectors.append({
            "name": name,
            "label": spec["label"],
            "locked": spec["locked"],
            "lockedNote": spec["lockedNote"],
            "options": spec["options"],
            "includedInTotalOption": _INCLUDED_OPTION,
            "values": settings["detectors"][name],
        })
    return {
        "detectors": detectors,
        "ensemble": {
            "method": settings["ensemble"]["method"],
            "methods": [{"value": value, "label": label, "hint": ENSEMBLE_METHOD_LABELS[value]}
                        for value, label in ENSEMBLE_METHODS],
            "weights": settings["ensemble"]["weights"],
        },
        "effectLabels": EFFECT_LABELS,
    }


def option_labels(name: str) -> dict[str, str]:
    """Human-readable option labels for one detector, used in saved results."""
    spec = DETECTOR_SCHEMA.get(name)
    if not spec:
        return {}
    labels = {_INCLUDED_OPTION["key"]: _INCLUDED_OPTION["label"]}
    labels.update({option["key"]: option["label"] for option in spec["options"]})
    return labels


__all__ = [
    "DEFAULT_ENSEMBLE",
    "DETECTOR_SCHEMA",
    "ENSEMBLE_METHODS",
    "EFFECT_LABELS",
    "EFFECT_SCORE",
    "EFFECT_TOTAL",
    "EFFECT_VERDICT",
    "OPTIONS_PATH",
    "current",
    "default_options",
    "describe",
    "for_detector",
    "included_in_total",
    "load",
    "merge",
    "normalize",
    "option_labels",
    "save",
]
