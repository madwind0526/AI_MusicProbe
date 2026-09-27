"""Detector registry.

A detector is a model that returns a probability or score for one file. None of
them ship with this repository: weights are downloaded on demand and every slot
reports honestly when it is empty rather than silently returning a number.

The DSP fingerprint in `probe.dsp` is always available and needs no download, so
the tool is useful before any model is fetched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable

from ..config import MODELS_DIR
from ..detector_options import describe as describe_options, for_detector

SETTINGS_PATH = MODELS_DIR / "detector-settings.json"


@dataclass
class Detector:
    name: str
    label: str
    license: str
    source: str
    weight_path: Path
    install_hint: str
    #: Returns a score dict for one decoded file. Set when the weight exists.
    run: Callable | None = None
    notes: str = ""
    extra: dict = field(default_factory=dict)
    enabled: bool = True
    required_paths: tuple[Path, ...] = ()

    @property
    def available(self) -> bool:
        return self.run is not None and self.weight_path.is_file() and all(path.is_file() for path in self.required_paths)

    def unavailable_reason(self) -> str:
        # Report missing files first: those are actionable for the user, whereas
        # an unconnected runtime is a development-time state that hides them.
        if not self.weight_path.is_file():
            return f"가중치 없음: {self.weight_path}"
        missing = next((path for path in self.required_paths if not path.is_file()), None)
        if missing is not None:
            return f"필수 파일 없음: {missing}"
        if self.run is None:
            return "런타임이 아직 연결되지 않았습니다."
        return ""

    @property
    def active(self) -> bool:
        return self.available and self.enabled

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "license": self.license,
            "source": self.source,
            "available": self.available,
            "enabled": self.enabled,
            "active": self.active,
            "reason": self.unavailable_reason(),
            "installHint": self.install_hint,
            "notes": self.notes,
            **self.extra,
        }


def _sonics() -> Detector:
    roots = sorted((MODELS_DIR / "sonics" / "cache").glob("models--awsaf49--sonics-spectttra-gamma-5s/snapshots/*"))
    model_dir = roots[-1] if roots else MODELS_DIR / "sonics" / "sonics-spectttra-gamma-5s"
    weight_path = model_dir / "pytorch_model.bin"
    runner = None
    if weight_path.is_file():
        try:
            from .sonics import create_runner

            runner = create_runner(model_dir)
        except ImportError:
            runner = None
    return Detector(
        name="sonics",
        label="SONICS / SpecTTTra gamma 5s",
        license="MIT (코드·모델), 데이터셋 CC BY-NC 4.0",
        source="github.com/awsaf49/sonics",
        weight_path=weight_path,
        install_hint="huggingface.co/awsaf49/sonics-spectttra-gamma-5s 모델을 models/sonics/cache 로 받습니다.",
        notes="Suno/Udio 로 학습됨. YuE2 등 로컬 엔진에 대한 일반화는 보장되지 않습니다.",
        run=runner,
    )


def _artifactnet() -> Detector:
    model_path = MODELS_DIR / "artifactnet" / "artifactnet_v94_full.onnx"
    data_path = MODELS_DIR / "artifactnet" / "artifactnet_v94_full.onnx.data"
    runner = None
    if model_path.is_file() and data_path.is_file():
        try:
            from .artifactnet import create_runner

            runner = create_runner(model_path)
        except ImportError:
            runner = None
    return Detector(
        name="artifactnet",
        label="ArtifactNet v9.4",
        license="CC BY-NC 4.0",
        source="huggingface.co/intrect/artifactnet",
        weight_path=model_path,
        required_paths=(data_path,),
        install_hint="huggingface.co/intrect/artifactnet 의 v9.4 ONNX와 외부 데이터 파일을 models/artifactnet/에 받습니다.",
        notes="코덱 RVQ 잔차 기반 연구용 모델입니다. 비상업 용도로만 사용할 수 있으며 특허 권리는 포함되지 않습니다.",
        run=runner,
    )


def _lofcz() -> Detector:
    weight_path = MODELS_DIR / "lofcz" / "ai-music-detector.onnx"
    runner = None
    if weight_path.is_file():
        try:
            from .lofcz import create_runner

            runner = create_runner(weight_path)
        except ImportError:
            runner = None
    return Detector(
        name="lofcz",
        label="lofcz vocoder fakeprint",
        license="MIT",
        source="github.com/lofcz/ai-music-detector",
        weight_path=weight_path,
        install_hint="github.com/lofcz/ai-music-detector 의 ONNX(~15KB)를 models/lofcz/ 로 받고 onnxruntime 설치.",
        notes="1~8kHz 보코더 재구성 아티팩트를 봅니다. 아키텍처 물리 기반이라 OOD에 강할 가능성이 큽니다.",
        run=runner,
    )


def _attribution() -> Detector:
    return Detector(
        name="attribution",
        label="생성기 어트리뷰션 헤드",
        license="직접 학습",
        source="probe/attribution (미구현)",
        weight_path=Path("corpus/attribution/head.pt"),
        install_hint="corpus/ 에 라벨 있는 코퍼스를 만든 뒤 MERT freeze + MLP 헤드를 학습해야 합니다.",
        notes="범용 모델로는 불가능합니다. 자기 코퍼스가 있어야 합니다.",
    )


DETECTORS: dict[str, Detector] = {
    detector.name: detector for detector in (_sonics(), _artifactnet(), _lofcz(), _attribution())
}


def _load_settings() -> dict[str, bool]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(name): bool(value) for name, value in data.items()}


for detector_name, is_enabled in _load_settings().items():
    if detector_name in DETECTORS:
        DETECTORS[detector_name].enabled = is_enabled


def describe() -> list[dict]:
    """Detector slots plus the analysis options currently in effect.

    Reports embed this, so a saved result always states which segment,
    aggregation, and threshold values produced its numbers.
    """
    schema = {item["name"]: item for item in describe_options()["detectors"]}
    out = []
    for detector in sorted(DETECTORS.values(), key=lambda item: item.label.casefold()):
        payload = detector.as_dict()
        entry = schema.get(detector.name, {})
        payload["options"] = for_detector(detector.name)
        payload["locked"] = entry.get("locked", [])
        payload["lockedNote"] = entry.get("lockedNote", "")
        out.append(payload)
    return out


def set_enabled(name: str, enabled: bool) -> dict:
    detector = DETECTORS.get(name)
    if detector is None:
        raise KeyError(name)
    if enabled and not detector.available:
        raise ValueError(detector.unavailable_reason())
    detector.enabled = enabled
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: item.enabled for key, item in sorted(DETECTORS.items())}
    temporary = SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(SETTINGS_PATH)
    return detector.as_dict()


def get(name: str) -> Detector | None:
    return DETECTORS.get(name)


def available_names() -> list[str]:
    return [name for name, detector in DETECTORS.items() if detector.active]


__all__ = ["DETECTORS", "Detector", "available_names", "describe", "get", "set_enabled"]
