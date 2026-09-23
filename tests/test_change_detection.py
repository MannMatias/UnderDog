"""Detección de cambios: cuándo una corrida programada reconstruye y cuándo
se saltea."""

from __future__ import annotations

import pytest

from include.src import change_detection as cd

SOURCE = [
    {"tabla": "match", "filas": 25979, "max_fecha": "2016-05-25 00:00:00", "hash_contenido": "a"},
    {"tabla": "player", "filas": 11060, "max_fecha": None, "hash_contenido": "b"},
]


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    silver = tmp_path / "underdog_dataset.parquet"
    manifest = tmp_path / "_manifest.json"
    monkeypatch.setattr(cd, "SILVER_DATASET_PATH", silver)
    monkeypatch.setattr(cd, "SILVER_MANIFEST_PATH", manifest)
    return silver


def _processed(silver, fingerprint):
    silver.write_bytes(b"parquet")
    cd.write_manifest(fingerprint, {"rows": 1}, run_id="test")


def test_first_run_rebuilds(isolated_state):
    rebuild, reason = cd.needs_rebuild(cd.build_fingerprint(SOURCE))
    assert rebuild and "no existe" in reason


def test_same_source_and_code_skips(isolated_state):
    fingerprint = cd.build_fingerprint(SOURCE)
    _processed(isolated_state, fingerprint)

    rebuild, _ = cd.needs_rebuild(cd.build_fingerprint(SOURCE))
    assert not rebuild


def test_new_matches_in_source_trigger_rebuild(isolated_state):
    _processed(isolated_state, cd.build_fingerprint(SOURCE))
    changed = [dict(SOURCE[0], filas=25980, max_fecha="2016-06-01 00:00:00"), SOURCE[1]]

    rebuild, reason = cd.needs_rebuild(cd.build_fingerprint(changed))
    assert rebuild and "fuente" in reason


def test_corrected_row_with_same_count_triggers_rebuild(isolated_state):
    _processed(isolated_state, cd.build_fingerprint(SOURCE))
    corrected = [dict(SOURCE[0], hash_contenido="otro"), SOURCE[1]]

    rebuild, _ = cd.needs_rebuild(cd.build_fingerprint(corrected))
    assert rebuild


def test_code_change_triggers_rebuild(isolated_state, monkeypatch):
    _processed(isolated_state, cd.build_fingerprint(SOURCE))
    monkeypatch.setattr(cd, "code_version", lambda: "otra-version")

    rebuild, reason = cd.needs_rebuild(cd.build_fingerprint(SOURCE))
    assert rebuild and "código" in reason


def test_force_rebuild_param_wins(isolated_state):
    fingerprint = cd.build_fingerprint(SOURCE)
    _processed(isolated_state, fingerprint)

    rebuild, reason = cd.needs_rebuild(fingerprint, force=True)
    assert rebuild and "force_rebuild" in reason


def test_missing_silver_rebuilds_even_with_same_fingerprint(isolated_state):
    fingerprint = cd.build_fingerprint(SOURCE)
    _processed(isolated_state, fingerprint)
    isolated_state.unlink()

    rebuild, _ = cd.needs_rebuild(fingerprint)
    assert rebuild


def test_code_version_ignores_line_endings(tmp_path, monkeypatch):
    unix, windows = tmp_path / "unix", tmp_path / "windows"
    for folder, text in ((unix, b"x = 1\n"), (windows, b"x = 1\r\n")):
        folder.mkdir()
        (folder / "config.py").write_bytes(text)
    versions = []
    for folder in (unix, windows):
        monkeypatch.setattr(cd, "INCLUDE_DIR", folder)
        monkeypatch.setattr(cd, "CODE_PATHS", [folder / "config.py"])
        versions.append(cd.code_version())
    assert versions[0] == versions[1]
