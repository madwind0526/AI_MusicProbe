"""HTTP API and static UI host for path-based and uploaded audio analysis."""

from __future__ import annotations

import json
import logging
import queue
import shutil
import threading
import csv
import io
from contextlib import AbstractContextManager, asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, dsp, history as history_module, report as report_module
from .app_settings import load_settings, save_settings
from .audioio import AudioToolError, load as load_audio
from .config import (
    HOST,
    MAX_ANALYSIS_ACTIVE,
    MAX_ANALYSIS_PENDING,
    MAX_UPLOAD_FILE_BYTES,
    MAX_UPLOAD_TOTAL_BYTES,
    PORT,
    REPORTS_DIR,
    SCRATCH_DIR,
)
from .detector_options import describe as describe_detector_options, load as load_detector_options, merge as merge_detector_options, save as save_detector_options
from .detectors import describe as describe_detectors, set_enabled as set_detector_enabled
from .file_analysis import analyze_files
from .file_browser import browse_directory
from .history import delete_history, load_history, save_history, set_favorite
from .resources import resource_snapshot
from .scratch_cleanup import cleanup_scratch
from .stages import StageError, StageSet, from_map, load as load_stage_set
from .visuals import render_audio_visual, validate_audio_path, waveform_peaks

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Guards the progress stream against a client that disconnects mid-analysis:
# without it the generator would block on the queue forever and leak a thread.
_PROGRESS_IDLE_TIMEOUT = 1800.0

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        removed = cleanup_scratch(SCRATCH_DIR, REPORTS_DIR, grace_seconds=0.0)
        if removed["uploads"] or removed["visuals"]:
            logging.getLogger(__name__).info(
                "Cleaned scratch files on startup: uploads=%d visuals=%d",
                removed["uploads"],
                removed["visuals"],
            )
    except OSError as error:
        logging.getLogger(__name__).warning("Startup scratch cleanup failed: %s", error)
    yield


app = FastAPI(
    title="ai-music-probe",
    version=__version__,
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=_lifespan,
)


def _cleanup_scratch(grace_seconds: float = 3600.0) -> None:
    try:
        cleanup_scratch(SCRATCH_DIR, REPORTS_DIR, grace_seconds)
    except OSError as error:
        logging.getLogger(__name__).warning("Scratch cleanup failed: %s", error)


def _save_history(payload: dict) -> None:
    save_history(payload)
    _cleanup_scratch(0.0)


class AnalysisReservation(AbstractContextManager):
    def __init__(self, owner: "AnalysisQueue") -> None:
        self.owner = owner
        self.entered = False

    def __enter__(self) -> "AnalysisReservation":
        self.owner.semaphore.acquire()
        with self.owner.lock:
            self.owner.active += 1
        self.entered = True
        return self

    def __exit__(self, *_args) -> None:
        with self.owner.lock:
            if self.entered:
                self.owner.active -= 1
            self.owner.submitted -= 1
        if self.entered:
            self.owner.semaphore.release()


class AnalysisQueue:
    def __init__(self, active_limit: int, pending_limit: int) -> None:
        self.active_limit = max(1, active_limit)
        self.pending_limit = max(0, pending_limit)
        self.semaphore = threading.BoundedSemaphore(self.active_limit)
        self.lock = threading.Lock()
        self.submitted = 0
        self.active = 0

    def reserve(self) -> AnalysisReservation:
        with self.lock:
            if self.submitted >= self.active_limit + self.pending_limit:
                raise HTTPException(status_code=429, detail="분석 대기열이 가득 찼습니다. 진행 중인 분석이 끝난 뒤 다시 시도해 주세요.")
            self.submitted += 1
        return AnalysisReservation(self)

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return {
                "active": self.active,
                "pending": max(0, self.submitted - self.active),
                "activeLimit": self.active_limit,
                "pendingLimit": self.pending_limit,
            }


_ANALYSIS_QUEUE = AnalysisQueue(MAX_ANALYSIS_ACTIVE, MAX_ANALYSIS_PENDING)


class AnalysisProgressTracker:
    """Keep one shared progress view for the WebUI, API clients, and other tabs."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tasks: dict[str, dict[str, Any]] = {}
        self.last: dict[str, Any] = {
            "state": "idle",
            "done": 0,
            "total": 0,
            "name": "분석 요청을 기다리고 있습니다.",
        }

    def begin(self) -> str:
        task_id = uuid4().hex
        with self.lock:
            self.tasks[task_id] = {"state": "queued", "done": 0, "total": 0, "name": "분석을 준비하고 있습니다."}
        return task_id

    def start(self, task_id: str) -> None:
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(state="running", name="음원 목록을 확인하고 있습니다.")

    def update(self, task_id: str, done: int, total: int, name: str | None) -> None:
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(state="running", done=max(0, done), total=max(0, total), name=name or "음원을 분석하고 있습니다.")

    def finish(self, task_id: str, state: str, done: int = 0, total: int = 0, name: str | None = None) -> None:
        with self.lock:
            self.tasks.pop(task_id, None)
            self.last = {
                "state": state,
                "done": max(0, done),
                "total": max(0, total),
                "name": name or ("모든 분석 작업을 완료했습니다." if state == "completed" else "분석 중 오류가 발생했습니다."),
            }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            for state in ("running", "queued"):
                for task in self.tasks.values():
                    if task["state"] == state:
                        return dict(task)
            return dict(self.last)


_ANALYSIS_PROGRESS = AnalysisProgressTracker()


class ScoreRequest(BaseModel):
    name: str = "stage-set"
    stages: dict[str, str] = Field(default_factory=dict)
    control_name: str | None = None
    control_stages: dict[str, str] = Field(default_factory=dict)
    save: bool = False


class AnalyzePathRequest(BaseModel):
    path: str
    name: str | None = None
    control_path: str | None = None
    control_name: str | None = None
    save: bool = False


class FileAnalyzeRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    path: str | None = None
    recursive: bool = True
    save: bool = False


class DetectorToggleRequest(BaseModel):
    enabled: bool


class DetectorValueRequest(BaseModel):
    """One detector's option values. Every field is optional so the WebUI can
    send a partial form and let the server fill in schema defaults."""

    includedInTotal: bool | None = None
    maxWindows: int | None = None
    hopSeconds: float | None = None
    aggregation: str | None = None
    topK: int | None = None
    maxDurationS: int | None = None
    analysisPosition: str | None = None
    segmentCount: int | None = None
    segmentSelection: str | None = None
    minValidSegments: int | None = None
    threshold: float | None = None
    levelNormalize: bool | None = None


class EnsembleRequest(BaseModel):
    method: str | None = None
    weights: dict[str, float] | None = None


class DetectorOptionsRequest(BaseModel):
    detectors: dict[str, DetectorValueRequest] = Field(default_factory=dict)
    ensemble: EnsembleRequest = Field(default_factory=EnsembleRequest)


class FavoriteRequest(BaseModel):
    favorite: bool


class ScoreBandSettings(BaseModel):
    thresholds: list[int]
    colors: list[str]


class PathSettings(BaseModel):
    music: str
    reports: str
    models: str


class AppSettingsRequest(BaseModel):
    scoreBands: ScoreBandSettings
    historyLimit: int = 0
    recursiveFolders: bool = True
    historyCardSize: int = 250
    variableHistoryCards: bool = True
    paths: PathSettings
    waveformPeaks: int = 180


def _run(target: StageSet, control: StageSet | None) -> dict:
    result = report_module.with_chain_flags(report_module.analyze(target, control))
    return result


def _maybe_save(result: dict, requested: bool, name: str) -> str | None:
    if not requested:
        return None
    stamp = result["generatedAt"].replace(":", "").replace("-", "")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:60] or "report"
    path = report_module.save(result, REPORTS_DIR / f"{stamp}-{safe}.json")
    return str(path)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "detectors": describe_detectors(),
        "analysisQueue": _ANALYSIS_QUEUE.snapshot(),
    }


@app.get("/api/detectors")
def detectors() -> dict:
    return {"detectors": describe_detectors()}


@app.get("/api/detector-options")
def get_detector_options() -> dict:
    return describe_detector_options()


@app.put("/api/detector-options")
def update_detector_options(request: DetectorOptionsRequest) -> dict:
    payload = request.model_dump(exclude_unset=True)
    merged = merge_detector_options(load_detector_options(), payload)
    try:
        return save_detector_options(merged)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"탐지기 설정을 저장하지 못했습니다: {exc}") from exc


@app.patch("/api/detectors/{name}")
def toggle_detector(name: str, request: DetectorToggleRequest) -> dict:
    try:
        return {"detector": set_detector_enabled(name, request.enabled)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="탐지기를 찾지 못했습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/files/browse")
def browse_files(path: str | None = None) -> dict:
    try:
        start = path if path is not None else load_settings()["paths"]["music"]
        return browse_directory(start)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings")
def get_app_settings() -> dict:
    return {"settings": load_settings()}


@app.put("/api/settings")
def update_app_settings(request: AppSettingsRequest) -> dict:
    global REPORTS_DIR
    previous = load_settings()
    try:
        settings = save_settings(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    REPORTS_DIR = Path(settings["paths"]["reports"])
    history_module.REPORTS_DIR = REPORTS_DIR
    history_module.HISTORY_DIR = REPORTS_DIR / "history"
    history_module.trim_history(settings["historyLimit"])
    _cleanup_scratch(0.0)
    return {
        "settings": settings,
        "restartRequired": previous["paths"]["models"] != settings["paths"]["models"],
    }


@app.get("/api/resources")
def resources() -> dict:
    return resource_snapshot()


@app.get("/api/history")
def history() -> dict:
    return {"results": load_history()}


@app.get("/api/history/signature")
def history_signature() -> dict:
    """Cheap change token so the UI can poll without refetching every result.

    The full payload carries per-detector segment data, which is far too heavy
    to pull every couple of seconds just to notice a new analysis landed.
    """
    return history_module.change_signature()


@app.patch("/api/history/favorite/{item_id:path}")
def favorite_history(item_id: str, request: FavoriteRequest) -> dict:
    if not set_favorite(item_id, request.favorite):
        raise HTTPException(status_code=404, detail="분석 이력을 찾지 못했습니다.")
    return {"favorite": request.favorite}


@app.delete("/api/history/{item_id:path}")
def remove_history(item_id: str) -> dict:
    if not delete_history(item_id):
        raise HTTPException(status_code=404, detail="분석 이력을 찾지 못했습니다.")
    _cleanup_scratch(0.0)
    return {"deleted": True}


@app.get("/api/media")
def media(path: str) -> FileResponse:
    try:
        source = validate_audio_path(path)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(source, filename=source.name)


@app.get("/api/audio/peaks")
def audio_peaks(path: str, count: int = 180) -> dict:
    try:
        return waveform_peaks(path, count)
    except (ValueError, OSError, AudioToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/audio/compare")
def audio_compare(source: str, target: str) -> dict:
    """Return readable band and level deltas for the two selected audio files."""
    if not source or not target:
        raise HTTPException(status_code=400, detail="비교할 음원 두 개가 필요합니다.")
    try:
        source_path = validate_audio_path(source)
        target_path = validate_audio_path(target)
        source_profile = dsp.analyze(load_audio(source_path))
        target_profile = dsp.analyze(load_audio(target_path))
    except (AudioToolError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"음원 비교를 계산하지 못했습니다: {exc}") from exc

    bands = (
        ("저음 ~200 Hz", 0.0, 200.0),
        ("중저음 200~1k", 200.0, 1000.0),
        ("중음 1~4k", 1000.0, 4000.0),
        ("중고음 4~8k", 4000.0, 8000.0),
        ("고음 8~12k", 8000.0, 12000.0),
        ("초고음 12k~", 12000.0, float("inf")),
    )

    def band_values(profile: dict, low: float, high: float) -> list[float]:
        values = []
        for key, value in (profile.get("spectral", {}).get("bandLevelsRelDb", {}) or {}).items():
            try:
                start, end = (float(part) for part in key.split("-", 1))
            except (TypeError, ValueError):
                continue
            if start >= low and end <= high and isinstance(value, (int, float)):
                values.append(float(value))
        return values

    changes = []
    for label, low, high in bands:
        before = band_values(source_profile, low, high)
        after = band_values(target_profile, low, high)
        source_value = sum(before) / len(before) if before else 0.0
        target_value = sum(after) / len(after) if after else 0.0
        changes.append({"label": label, "changeDb": round(target_value - source_value, 1)})

    source_levels = source_profile.get("levels", {})
    target_levels = target_profile.get("levels", {})

    def delta(key: str) -> float:
        before = source_levels.get(key)
        after = target_levels.get(key)
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            return 0.0
        return round(float(after) - float(before), 1)

    return {
        "bands": changes,
        "summary": {
            "rmsDb": delta("rmsDbfs"),
            "peakDb": delta("peakDbfs"),
            "truePeakDb": delta("truePeakDbfs"),
        },
    }


@app.get("/api/audio/{kind}")
def audio_visual(kind: str, path: str) -> FileResponse:
    try:
        image = render_audio_visual(path, kind)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(image, media_type="image/png")


@app.post("/api/score")
def score(request: ScoreRequest) -> dict:
    if not request.stages:
        raise HTTPException(status_code=400, detail="stage 를 하나 이상 지정해야 합니다.")
    try:
        target = from_map(request.name, request.stages)
        control = from_map(request.control_name or "control", request.control_stages) if request.control_stages else None
        with _ANALYSIS_QUEUE.reserve():
            result = _run(target, control)
    except (StageError, AudioToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = _maybe_save(result, request.save, request.name)
    if saved:
        result["savedTo"] = saved
    return result


@app.post("/api/analyze/stages")
def analyze_stages(request: AnalyzePathRequest) -> dict:
    try:
        target = load_stage_set(request.path)
        control = load_stage_set(request.control_path) if request.control_path else None
        if request.name:
            target = StageSet(name=request.name, stages=target.stages)
        if control is not None and request.control_name:
            control = StageSet(name=request.control_name, stages=control.stages)
        with _ANALYSIS_QUEUE.reserve():
            result = _run(target, control)
    except (StageError, AudioToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = _maybe_save(result, request.save, target.name)
    if saved:
        result["savedTo"] = saved
    return result


@app.post("/api/analyze")
def analyze(request: FileAnalyzeRequest) -> dict:
    paths = [*request.paths]
    if request.path:
        paths.append(request.path)
    if not paths:
        raise HTTPException(status_code=400, detail="분석할 파일 또는 폴더 경로가 필요합니다.")
    with _ANALYSIS_QUEUE.reserve():
        result = analyze_files(paths, recursive=request.recursive)
    if result["inputCount"] == 0:
        raise HTTPException(status_code=400, detail="지원하는 음원 파일을 찾지 못했습니다.")
    if request.save:
        saved = _maybe_save(result, True, "file-analysis")
        if saved:
            result["savedTo"] = saved
    _save_history(result)
    return result


async def _store_uploads(files: list[UploadFile]) -> tuple[list[Path], list[str]]:
    if not files:
        raise HTTPException(status_code=400, detail="분석할 음원 파일이 필요합니다.")
    _cleanup_scratch()
    root = SCRATCH_DIR / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    original_names: list[str] = []
    total_size = 0
    try:
        for index, upload in enumerate(files):
            original = Path(upload.filename or f"upload-{index}").name
            suffix = Path(original).suffix.lower()
            if suffix not in {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}:
                continue
            target = root / f"{uuid4().hex}-{original}"
            paths.append(target)
            size = 0
            with target.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total_size += len(chunk)
                    if size > MAX_UPLOAD_FILE_BYTES:
                        raise HTTPException(status_code=413, detail=f"파일이 너무 큽니다: {original}")
                    if total_size > MAX_UPLOAD_TOTAL_BYTES:
                        raise HTTPException(status_code=413, detail="한 번에 업로드한 파일의 전체 용량이 1 GB를 초과했습니다.")
                    output.write(chunk)
            original_names.append(original)
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    if not paths:
        raise HTTPException(status_code=400, detail="지원하는 음원 파일을 찾지 못했습니다.")
    return paths, original_names


def _restore_upload_names(result: dict, paths: list[Path], original_names: list[str]) -> None:
    names_by_path = {
        str(path.resolve()).casefold(): original
        for path, original in zip(paths, original_names)
    }
    for item in result.get("results", []):
        if not isinstance(item, dict):
            continue
        key = str(Path(str(item.get("file") or "")).resolve()).casefold()
        if key in names_by_path:
            item["name"] = names_by_path[key]


@app.post("/api/analyze/upload")
async def analyze_upload(files: list[UploadFile] = File(...)) -> dict:
    paths, original_names = await _store_uploads(files)
    with _ANALYSIS_QUEUE.reserve():
        result = analyze_files(paths, recursive=False)
    _restore_upload_names(result, paths, original_names)
    _save_history(result)
    return result


def _progress_response(
    run: Callable[[Callable[[dict], None]], None],
    reservation: AnalysisReservation,
) -> StreamingResponse:
    """Run `run(emit)` on a worker thread and stream its events as SSE.

    The detector work is CPU bound and blocks, so it cannot emit from inside a
    generator. A queue lets the worker push progress while the response body
    drains it, which is what makes a live (yy/zz) counter possible.
    """
    events: queue.Queue = queue.Queue()
    task_id = _ANALYSIS_PROGRESS.begin()

    def publish(item: dict) -> None:
        if "done" in item:
            _ANALYSIS_PROGRESS.update(
                task_id,
                int(item.get("done") or 0),
                int(item.get("total") or 0),
                str(item.get("name") or "") or None,
            )
        elif "result" in item:
            summary = item["result"].get("summary", {}) if isinstance(item["result"], dict) else {}
            completed = int(summary.get("completed") or 0)
            failed = int(summary.get("failed") or 0)
            total = completed + failed
            _ANALYSIS_PROGRESS.finish(task_id, "completed", total, total)
        elif "error" in item:
            _ANALYSIS_PROGRESS.finish(task_id, "failed", name=str(item.get("error") or ""))
        events.put(item)

    def worker() -> None:
        try:
            with reservation:
                _ANALYSIS_PROGRESS.start(task_id)
                run(publish)
        except Exception as error:  # noqa: BLE001
            publish({"error": str(error) or "분석 중 오류가 발생했습니다."})
        finally:
            events.put(None)

    def stream():
        threading.Thread(target=worker, daemon=True).start()
        while True:
            try:
                item = events.get(timeout=_PROGRESS_IDLE_TIMEOUT)
            except queue.Empty:
                yield f"data: {json.dumps({'error': '분석 응답이 시간 초과로 중단되었습니다.'}, ensure_ascii=False)}\n\n"
                break
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/analysis/status")
def analysis_status() -> dict[str, Any]:
    """Return the latest shared analysis state for sidebar progress polling."""
    return _ANALYSIS_PROGRESS.snapshot()


def _progress_emitter(emit: Callable[[dict], None]) -> Callable[[int, int, Path | None], None]:
    def on_progress(done: int, total: int, path: Path | None) -> None:
        emit({"done": done, "total": total, "name": path.name if path else None})

    return on_progress


@app.post("/api/analyze/progress")
def analyze_progress(request: FileAnalyzeRequest) -> StreamingResponse:
    """Stream per-file progress so the UI can show (yy/zz) while files run."""
    paths = [*request.paths]
    if request.path:
        paths.append(request.path)
    if not paths:
        raise HTTPException(status_code=400, detail="분석할 파일 또는 폴더 경로가 필요합니다.")

    def run(emit: Callable[[dict], None]) -> None:
        result = analyze_files(paths, recursive=request.recursive, on_progress=_progress_emitter(emit))
        if result["inputCount"] == 0:
            emit({"error": "지원하는 음원 파일을 찾지 못했습니다."})
            return
        if request.save:
            saved = _maybe_save(result, True, "file-analysis")
            if saved:
                result["savedTo"] = saved
        _save_history(result)
        emit({"result": result})

    return _progress_response(run, _ANALYSIS_QUEUE.reserve())


@app.post("/api/analyze/upload/progress")
async def analyze_upload_progress(files: list[UploadFile] = File(...)) -> StreamingResponse:
    paths, original_names = await _store_uploads(files)

    def run(emit: Callable[[dict], None]) -> None:
        def on_progress(done: int, total: int, path: Path | None) -> None:
            index = paths.index(path) if path is not None and path in paths else done - 1
            name = original_names[index] if 0 <= index < len(original_names) else (path.name if path else None)
            emit({"done": done, "total": total, "name": name})

        result = analyze_files(paths, recursive=False, on_progress=on_progress)
        _restore_upload_names(result, paths, original_names)
        _save_history(result)
        emit({"result": result})

    return _progress_response(run, _ANALYSIS_QUEUE.reserve())


@app.get("/api/reports")
def list_reports() -> dict:
    if not REPORTS_DIR.is_dir():
        return {"reports": []}
    items = []
    candidates = []
    for file in REPORTS_DIR.glob("*.json"):
        try:
            candidates.append((file.stat().st_mtime, file))
        except OSError:
            continue
    for _modified, file in sorted(candidates, key=lambda item: item[0], reverse=True)[:100]:
        try:
            stat = file.stat()
        except OSError:
            continue
        created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            created_at = str(payload.get("generatedAt") or created_at)
        except (OSError, json.JSONDecodeError):
            pass
        items.append({"name": file.name, "path": str(file), "sizeBytes": stat.st_size, "createdAt": created_at})
    return {"reports": items}


def _report_path(name: str) -> Path:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="리포트 이름이 올바르지 않습니다.")
    path = REPORTS_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    return path


def _report_csv(payload: dict) -> str:
    if isinstance(payload.get("results"), list):
        rows = payload["results"]
    elif isinstance(payload.get("pairs"), list):
        rows = payload["pairs"]
    else:
        rows = [payload]
    detector_names = sorted({
        str(detector.get("name"))
        for row in rows
        if isinstance(row, dict)
        for detector in row.get("detectors", [])
        if detector.get("name")
    })
    fieldnames = ["name", "file", "status", "totalScore", "confidence", "conclusion", *[f"detector:{name}" for name in detector_names]]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        detectors = {
            str(item.get("name")): round(float(item["score"]) * 100.0, 4)
            for item in row.get("detectors", [])
            if isinstance(item, dict) and item.get("name") and isinstance(item.get("score"), (int, float))
        }
        record = {key: row.get(key, "") for key in fieldnames[:6]}
        record.update({f"detector:{name}": detectors.get(name, "") for name in detector_names})
        writer.writerow(record)
    return "\ufeff" + output.getvalue()


@app.get("/api/reports/{name}/export")
def export_report(name: str, format: str = "json") -> Response:
    path = _report_path(name)
    export_format = format.lower()
    if export_format == "json":
        return FileResponse(path, media_type="application/json", filename=path.name)
    if export_format != "csv":
        raise HTTPException(status_code=400, detail="내보내기 형식은 json 또는 csv여야 합니다.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"리포트를 읽지 못했습니다: {exc}") from exc
    filename = f"{path.stem}.csv"
    return Response(
        content=_report_csv(payload).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.get("/api/reports/{name}")
def read_report(name: str) -> Any:
    path = _report_path(name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"리포트를 읽지 못했습니다: {exc}") from exc


@app.delete("/api/reports/{name}")
def delete_report(name: str) -> dict:
    path = _report_path(name)
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"리포트를 삭제하지 못했습니다: {exc}") from exc
    _cleanup_scratch(0.0)
    return {"deleted": True, "name": name}


@app.exception_handler(AudioToolError)
def _audio_error(_request, exc: AudioToolError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


class NoCacheStatic(StaticFiles):
    """Always revalidate web assets.

    The WebUI is edited constantly during development. Without an explicit
    Cache-Control the browser applies a heuristic freshness lifetime and keeps
    serving a stale app.js, so UI changes appear to do nothing until a hard
    reload. no-cache still allows conditional requests via ETag, so it is cheap.
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


if WEB_DIR.is_dir():
    app.mount("/", NoCacheStatic(directory=WEB_DIR, html=True), name="web")


class _QuietPollingEndpoints(logging.Filter):
    """The top bar polls /api/resources and /api/history/signature every few seconds, a history
    change triggers a plain /api/history refetch, and SongYUE2's Settings page polls /health (every
    3s while open, every 1s while its "server starting" state is shown) to drive its running/off
    badge - useful traffic, but at this rate it drowns out every other request in the console.
    Everything else still logs normally."""

    _quiet_markers = ("GET /api/resources ", "GET /api/history ", "GET /api/history/signature ", "GET /health ")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(marker in message for marker in self._quiet_markers)


def main() -> None:
    import uvicorn

    logging.getLogger("uvicorn.access").addFilter(_QuietPollingEndpoints())
    print(f"ai-music-probe {__version__}  ->  http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
