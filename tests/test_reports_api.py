import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from probe import app


def test_list_reports_includes_generated_time_and_delete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app, "REPORTS_DIR", tmp_path)
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
