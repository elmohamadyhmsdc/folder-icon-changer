import os

import pytest

from app.services import organizer


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    monkeypatch.setattr(organizer, "data_dir", lambda: str(tmp_path / "appdata"))
    os.makedirs(tmp_path / "appdata", exist_ok=True)


@pytest.mark.parametrize("filename, expected", [
    ("Inception.2010.1080p.BluRay.x264-GROUP.mkv", "Inception (2010)"),
    ("The Matrix (1999) [1080p].mp4", "The Matrix (1999)"),
    ("1917.2019.1080p.WEB-DL.mkv", "1917 (2019)"),
    ("1917.mkv", "1917"),
    ("Wonder.Woman.1984.2020.BluRay.mkv", "Wonder Woman 1984 (2020)"),
    ("blade runner 2049 2017 720p.avi", "Blade Runner 2049 (2017)"),
    ("Spider-Man: No Way Home (2021).mkv", "Spider-Man - No Way Home (2021)"),
    ("[YTS] Parasite.2019.mp4", "Parasite (2019)"),
    ("Movie.Name.mkv", "Movie Name"),
])
def test_folder_name_for(filename, expected):
    assert organizer.folder_name_for(filename)[0] == expected


def test_sanitize_removes_invalid_characters():
    assert organizer.sanitize_folder_name('What?: "Is" <this>*') == "What - Is this"
    assert organizer.sanitize_folder_name("Name. ") == "Name"


def test_tv_episode_detection():
    assert organizer.is_tv_episode("Show.Name.S01E02.1080p.mkv")
    assert organizer.is_tv_episode("Show 1x05.avi")
    assert not organizer.is_tv_episode("Movie 2010.mkv")


def _make(tmp_path, names, size=10):
    for n in names:
        (tmp_path / n).write_bytes(b"x" * size)


def test_scan_finds_loose_movies_sidecars_and_skips(tmp_path):
    _make(tmp_path, [
        "Inception.2010.1080p.mkv", "Inception.2010.1080p.srt", "Inception.2010.1080p.en.srt",
        "Show.S01E01.mkv", "Heat.1995.mkv", "notes.txt",
    ])
    (tmp_path / "Already Organized").mkdir()
    (tmp_path / "Already Organized" / "Film.mkv").write_bytes(b"x")

    moves, skipped = organizer.scan_loose_movies(str(tmp_path))
    names = {m.folder_name for m in moves}
    assert names == {"Inception (2010)", "Heat (1995)"}      # subfolder contents are not loose
    inception = next(m for m in moves if m.title == "Inception")
    assert len(inception.sidecars) == 2
    assert [n for n, _ in skipped] == ["Show.S01E01.mkv"]


def test_execute_moves_files_and_undo_restores(tmp_path):
    _make(tmp_path, ["Inception.2010.mkv", "Inception.2010.srt", "Heat.1995.mkv"])
    moves, _ = organizer.scan_loose_movies(str(tmp_path))
    res = organizer.execute(moves, str(tmp_path))

    assert res.moved == 2 and not res.errors
    assert (tmp_path / "Inception (2010)" / "Inception.2010.mkv").exists()
    assert (tmp_path / "Inception (2010)" / "Inception.2010.srt").exists()
    assert (tmp_path / "Heat (1995)" / "Heat.1995.mkv").exists()
    assert not (tmp_path / "Heat.1995.mkv").exists()

    icon_calls = []
    restored, errors = organizer.undo_last_batch(lambda f: icon_calls.append(f) or True)
    assert restored == 2 and not errors
    assert len(icon_calls) == 2
    assert (tmp_path / "Heat.1995.mkv").exists()
    assert (tmp_path / "Inception.2010.srt").exists()
    assert not (tmp_path / "Inception (2010)").exists()      # folder we created is removed
    assert organizer.last_batch_summary() is None


def test_execute_merges_into_existing_folder_and_never_overwrites(tmp_path):
    (tmp_path / "Heat (1995)").mkdir()
    (tmp_path / "Heat (1995)" / "Heat.1995.mkv").write_bytes(b"old")
    _make(tmp_path, ["Heat.1995.mkv"])

    moves, _ = organizer.scan_loose_movies(str(tmp_path))
    assert moves[0].blocked and "already exists" in moves[0].note
    res = organizer.execute(moves, str(tmp_path))
    assert res.moved == 0
    assert (tmp_path / "Heat (1995)" / "Heat.1995.mkv").read_bytes() == b"old"
    assert (tmp_path / "Heat.1995.mkv").exists()


def test_existing_folder_without_clash_is_allowed(tmp_path):
    (tmp_path / "Heat (1995)").mkdir()
    _make(tmp_path, ["Heat.1995.mkv"])
    moves, _ = organizer.scan_loose_movies(str(tmp_path))
    assert not moves[0].blocked and "exists" in moves[0].note
    assert organizer.execute(moves, str(tmp_path)).moved == 1


def test_undo_keeps_preexisting_folder(tmp_path):
    (tmp_path / "Heat (1995)").mkdir()
    _make(tmp_path, ["Heat.1995.mkv"])
    moves, _ = organizer.scan_loose_movies(str(tmp_path))
    organizer.execute(moves, str(tmp_path))
    organizer.undo_last_batch()
    assert (tmp_path / "Heat (1995)").is_dir()               # not created by us -> not removed
    assert (tmp_path / "Heat.1995.mkv").exists()


def test_unselected_and_blocked_are_not_moved(tmp_path):
    _make(tmp_path, ["A.2001.mkv", "B.2002.mkv"])
    moves, _ = organizer.scan_loose_movies(str(tmp_path))
    moves[0].selected = False
    res = organizer.execute(moves, str(tmp_path))
    assert res.moved == 1
    assert (tmp_path / "A.2001.mkv").exists()
