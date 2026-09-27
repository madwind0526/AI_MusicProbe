import json

from probe.scratch_cleanup import cleanup_scratch
from probe.visuals import visual_cache_path


def test_cleanup_removes_only_unreferenced_uploads_and_visuals(tmp_path) -> None:
    scratch = tmp_path / "scratch"
    uploads = scratch / "uploads"
    visuals = scratch / "visuals"
    reports = tmp_path / "reports"
    history = reports / "history"
    uploads.mkdir(parents=True)
    visuals.mkdir(parents=True)
    history.mkdir(parents=True)

    referenced = uploads / "referenced.wav"
    orphan = uploads / "orphan.wav"
    referenced.write_bytes(b"audio")
    orphan.write_bytes(b"audio")
    (history / "run.json").write_text(
        json.dumps({"results": [{"file": str(referenced)}]}),
        encoding="utf-8",
    )

    expected_visual = visual_cache_path(referenced.resolve(), "waveform", visuals)
    stale_visual = visuals / "stale.png"
    expected_visual.write_bytes(b"png")
    stale_visual.write_bytes(b"png")

    result = cleanup_scratch(scratch, reports, grace_seconds=0)

    assert result == {"uploads": 1, "visuals": 1}
    assert referenced.is_file()
    assert expected_visual.is_file()
    assert not orphan.exists()
    assert not stale_visual.exists()


def test_cleanup_keeps_recent_orphan_during_grace_period(tmp_path) -> None:
    scratch = tmp_path / "scratch"
    uploads = scratch / "uploads"
    uploads.mkdir(parents=True)
    recent = uploads / "recent.wav"
    recent.write_bytes(b"audio")

    result = cleanup_scratch(scratch, tmp_path / "reports", grace_seconds=3600)

    assert result["uploads"] == 0
    assert recent.is_file()
