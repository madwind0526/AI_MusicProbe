"""HTTP API and static UI host for path-based and uploaded audio analysis."""

from __future__ import annotations

import json
import shutil
from uuid import uuid4
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, history as history_module, report as report_module
from .app_settings import load_settings, save_settings
from .audioio import AudioToolError
from .config import HOST, PORT, REPORTS_DIR, SCRATCH_DIR
from .detectors import describe as describe_detectors, set_enabled as set_detector_enabled
from .file_analysis import analyze_files
from .file_browser import browse_directory
from .history import delete_history, load_history, save_history, set_favorite
from .resources import resource_snapshot
from .stages import StageError, StageSet, from_map, load as load_stage_set
from .visuals import render_audio_visual, validate_audio_path, waveform_peaks

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="ai-music-probe", version=__version__, docs_url="/api/docs", redoc_url=None)


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
    }


@app.get("/api/detectors")
def detectors() -> dict:
    return {"detectors": describe_detectors()}


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


@app.patch("/api/history/favorite/{item_id:path}")
def favorite_history(item_id: str, request: FavoriteRequest) -> dict:
    if not set_favorite(item_id, request.favorite):
        raise HTTPException(status_code=404, detail="분석 이력을 찾지 못했습니다.")
    return {"favorite": request.favorite}


@app.delete("/api/history/{item_id:path}")
def remove_history(item_id: str) -> dict:
    if not delete_history(item_id):
        raise HTTPException(status_code=404, detail="분석 이력을 찾지 못했습니다.")
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
    result = analyze_files(paths, recursive=request.recursive)
    if result["inputCount"] == 0:
        raise HTTPException(status_code=400, detail="지원하는 음원 파일을 찾지 못했습니다.")
    if request.save:
        saved = _maybe_save(result, True, "file-analysis")
        if saved:
            result["savedTo"] = saved
    save_history(result)
    return result


@app.post("/api/analyze/upload")
async def analyze_upload(files: list[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="분석할 음원 파일이 필요합니다.")
    root = SCRATCH_DIR / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    original_names = []
    for index, upload in enumerate(files):
        original = Path(upload.filename or f"upload-{index}").name
        suffix = Path(original).suffix.lower()
        if suffix not in {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}:
            continue
        target = root / f"{uuid4().hex}-{original}"
        size = 0
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > 500 * 1024 * 1024:
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"파일이 너무 큽니다: {original}")
                output.write(chunk)
        paths.append(target)
        original_names.append(original)
    if not paths:
        raise HTTPException(status_code=400, detail="지원하는 음원 파일을 찾지 못했습니다.")
    result = analyze_files(paths, recursive=False)
    for item, original in zip(result["results"], original_names):
        item["name"] = original
    save_history(result)
    return result


@app.get("/api/reports")
def list_reports() -> dict:
    if not REPORTS_DIR.is_dir():
        return {"reports": []}
    items = []
    for file in sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        items.append({"name": file.name, "path": str(file), "sizeBytes": file.stat().st_size})
    return {"reports": items}


@app.get("/api/reports/{name}")
def read_report(name: str) -> Any:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="리포트 이름이 올바르지 않습니다.")
    path = REPORTS_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.exception_handler(AudioToolError)
def _audio_error(_request, exc: AudioToolError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


def main() -> None:
    import uvicorn

    print(f"ai-music-probe {__version__}  ->  http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
