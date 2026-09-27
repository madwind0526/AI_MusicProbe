import json
import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from probe import app


def test_list_reports_includes_generated_time_and_delete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(app, "SCRATCH_DIR", tmp_path / "scratch")
    target = tmp_path / "saved.json"
    target.write_text(json.dumps({"generatedAt": "2026-09-27T12:34:56+09:00"}), encoding="utf-8")

    reports = app.list_reports()["reports"]

    assert reports[0]["createdAt"] == "2026-09-27T12:34:56+09:00"
    assert app.delete_report("saved.json") == {"deleted": True, "name": "saved.json"}
    assert not target.exists()


def test_delete_report_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app, "REPORTS_DIR", tmp_path)

    with pytest.raises(HTTPException) as error:
        app.delete_report("../outside.json")

    assert error.value.status_code == 400


def test_export_report_as_csv_flattens_detector_scores(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app, "REPORTS_DIR", tmp_path)
    payload = {
        "results": [{
            "name": "sample.flac",
            "file": "C:/music/sample.flac",
            "status": "completed",
            "totalScore": 87.5,
            "confidence": 91.0,
            "conclusion": "AI 생성 흔적이 매우 강함",
            "detectors": [{"name": "sonics", "score": 0.8}, {"name": "lofcz", "score": 0.95}],
        }]
    }
    (tmp_path / "saved.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    response = app.export_report("saved.json", "csv")
    content = response.body.decode("utf-8-sig")

    assert "detector:lofcz" in content
    assert "detector:sonics" in content
    assert "sample.flac" in content
    assert "95.0" in content


def test_analysis_queue_rejects_requests_beyond_pending_limit() -> None:
    analysis_queue = app.AnalysisQueue(active_limit=1, pending_limit=1)
    running = analysis_queue.reserve()
    running.__enter__()
    waiting = analysis_queue.reserve()

    assert analysis_queue.snapshot() == {"active": 1, "pending": 1, "activeLimit": 1, "pendingLimit": 1}
    with pytest.raises(HTTPException) as error:
        analysis_queue.reserve()
    assert error.value.status_code == 429

    running.__exit__(None, None, None)
    with waiting:
        assert analysis_queue.snapshot()["active"] == 1
    assert analysis_queue.snapshot()["active"] == 0


def test_analysis_progress_tracker_prefers_running_and_keeps_last_result() -> None:
    tracker = app.AnalysisProgressTracker()
    queued = tracker.begin()
    running = tracker.begin()
    tracker.start(running)
    tracker.update(running, 2, 4, "second.wav")

    assert tracker.snapshot() == {"state": "running", "done": 2, "total": 4, "name": "second.wav"}

    tracker.finish(running, "completed", 4, 4)
    assert tracker.snapshot()["state"] == "queued"

    tracker.start(queued)
    tracker.finish(queued, "completed", 3, 3)
    assert tracker.snapshot() == {
        "state": "completed",
        "done": 3,
        "total": 3,
        "name": "모든 분석 작업을 완료했습니다.",
    }


def test_upload_total_size_limit_removes_partial_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app, "SCRATCH_DIR", tmp_path)
    monkeypatch.setattr(app, "MAX_UPLOAD_FILE_BYTES", 10)
    monkeypatch.setattr(app, "MAX_UPLOAD_TOTAL_BYTES", 6)
    uploads = [
        UploadFile(filename="one.wav", file=BytesIO(b"1234")),
        UploadFile(filename="two.wav", file=BytesIO(b"5678")),
    ]

    with pytest.raises(HTTPException) as error:
        asyncio.run(app._store_uploads(uploads))

    assert error.value.status_code == 413
    assert list((tmp_path / "uploads").glob("*")) == []


def test_restore_upload_names_uses_file_path_instead_of_result_order(tmp_path: Path) -> None:
    first = tmp_path / "b-random.wav"
    second = tmp_path / "a-random.wav"
    result = {"results": [
        {"file": str(second), "name": second.name},
        {"file": str(first), "name": first.name},
    ]}

    app._restore_upload_names(result, [first, second], ["first.wav", "second.wav"])

    assert [item["name"] for item in result["results"]] == ["second.wav", "first.wav"]


def test_read_report_returns_client_error_for_invalid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app, "REPORTS_DIR", tmp_path)
    (tmp_path / "broken.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(HTTPException) as error:
        app.read_report("broken.json")

    assert error.value.status_code == 400
