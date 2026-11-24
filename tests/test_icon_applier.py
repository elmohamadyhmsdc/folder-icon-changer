import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")

from app.services import icon_applier  # noqa: E402

CRLF = chr(13) + chr(10)


@pytest.fixture
def env(tmp_path, monkeypatch):
    undo = tmp_path / "undo"
    undo.mkdir()
    monkeypatch.setattr(icon_applier, "undo_dir", lambda: str(undo))
    monkeypatch.setattr(icon_applier, "_refresh_explorer", lambda: None)
    folder = tmp_path / "folder"
    folder.mkdir()
    ico = tmp_path / "src.ico"
    ico.write_bytes(b"ico")
    return folder, ico


def _read_ini(folder):
    with open(folder / "desktop.ini", encoding="utf-16", newline="") as f:
        return f.read().replace(CRLF, "\n")


def test_undo_restores_original_after_double_apply(env):
    folder, ico = env
    original = "[.ShellClassInfo]\nLocalizedResourceName=Original\n"
    (folder / "desktop.ini").write_text(original, encoding="utf-16")  # text mode -> CRLF on disk

    assert icon_applier.apply(str(folder), str(ico))[0]
    assert icon_applier.apply(str(folder), str(ico))[0]   # second apply must not clobber undo state
    assert "IconFile=folder.ico" in _read_ini(folder)

    assert icon_applier.undo(str(folder))
    assert not (folder / "folder.ico").exists()
    assert _read_ini(folder) == original


def test_undo_without_desktop_ini_removes_files(env):
    folder, ico = env
    assert icon_applier.apply(str(folder), str(ico))[0]
    assert icon_applier.undo(str(folder))
    assert not os.path.exists(folder / "desktop.ini")
    assert not os.path.exists(folder / "folder.ico")
