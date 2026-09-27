from pathlib import Path

from probe.stages import from_directory


def test_songyue_source_files_are_preserved_as_distinct_stages(tmp_path: Path) -> None:
    stems = tmp_path / "stems"
    stems.mkdir()
    original = stems / "source.wav"
    converted = stems / "source-44k.wav"
    original.touch()
    converted.touch()

    stage_set = from_directory(tmp_path)

    assert stage_set.stages["source_original"] == original.resolve()
    assert stage_set.stages["source_44k"] == converted.resolve()
    assert [name for name, _path in stage_set.ordered()][:2] == ["source_original", "source_44k"]
