"""Put loose movie files into their own, properly named folders.

A "loose" movie is a video file that sits directly inside a library folder
(e.g. ``D:\\Movies\\Inception.2010.1080p.BluRay.mkv``) instead of inside a
folder of its own. Folder icons can only be set on folders, so each such file
is moved into ``D:\\Movies\\Inception (2010)\\`` together with its subtitles.

Nothing is ever deleted or overwritten, and every batch is logged so it can be
reverted with :func:`undo_last_batch`.
"""
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from app.config import data_dir

VIDEO_EXTS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".mpg", ".mpeg",
    ".ts", ".m2ts", ".webm", ".flv", ".divx", ".iso",
}
SIDECAR_EXTS = {".srt", ".sub", ".idx", ".ass", ".ssa", ".vtt", ".sup", ".nfo"}

_SAMPLE_MAX_BYTES = 100 * 1024 * 1024

_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20[0-2]\d)(?!\d)")
_PAREN_YEAR_RE = re.compile(r"[\(\[]\s*(19\d{2}|20[0-2]\d)\s*[\)\]]")
_TAG_RE = re.compile(
    r"(?<![A-Za-z0-9])("
    r"480p|576p|720p|1080p|1080i|2160p|4k|uhd|"
    r"blu-?ray|bdrip|brrip|bdremux|remux|web-?dl|webrip|hdtv|dvdrip|dvdscr|hdrip|hdcam|"
    r"x264|x265|h\.?264|h\.?265|hevc|xvid|10bit|hdr10?|"
    r"aac|ac3|eac3|dts(?:-hd)?|ddp?5\.1|truehd|flac|"
    r"unrated|repack|imax|subbed|dubbed"
    r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_TV_RE = re.compile(r"(?<![A-Za-z0-9])(S\d{1,2}[ ._-]?E\d{1,3}|\d{1,2}x\d{2,3}|Episode[ ._-]?\d+)(?![A-Za-z0-9])", re.IGNORECASE)
_INVALID_CHARS_RE = re.compile(r'[<>"/\\|?*\x00-\x1f]')


# ── Naming ────────────────────────────────────────────────────────────

def sanitize_folder_name(name: str) -> str:
    """Make a string safe to use as a Windows folder name."""
    name = name.replace(":", " -")
    name = _INVALID_CHARS_RE.sub("", name)
    name = re.sub(r"\s{2,}", " ", name).strip().rstrip(". ")
    return name


def parse_movie_filename(filename: str) -> Tuple[str, str]:
    """Return ``(title, year)`` guessed from a movie file name (year may be '')."""
    stem = os.path.splitext(filename)[0]

    year = ""
    m = _PAREN_YEAR_RE.search(stem)
    if m:
        year = m.group(1)
    # Drop [Group] tags and (anything) in parentheses.
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", stem)
    text = re.sub(r"[._]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    tag = _TAG_RE.search(text)
    limit = tag.start() if tag else len(text)

    if not year:
        # Last plausible year before the first release tag. A year at index 0 is
        # part of the title ("1917", "2012") and is never treated as the year.
        years = [y for y in _YEAR_RE.finditer(text) if y.start() > 0 and y.end() <= limit]
        if years:
            y = years[-1]
            year = y.group(1)
            limit = y.start()

    title = text[:limit].strip(" -–—")
    if not title:
        title = text.strip(" -–—") or stem
    if title.islower() or title.isupper():
        title = title.title()
    return sanitize_folder_name(title), year


def folder_name_for(filename: str) -> Tuple[str, str, str]:
    """Return ``(folder_name, title, year)`` for a movie file name."""
    title, year = parse_movie_filename(filename)
    if not title:
        title = sanitize_folder_name(os.path.splitext(filename)[0]) or "Movie"
    name = f"{title} ({year})" if year else title
    return sanitize_folder_name(name), title, year


def is_tv_episode(filename: str) -> bool:
    return bool(_TV_RE.search(os.path.splitext(filename)[0]))


# ── Scanning ──────────────────────────────────────────────────────────

@dataclass
class MovieMove:
    source: str                       # full path of the video file
    folder_name: str                  # proposed (editable) folder name
    title: str = ""
    year: str = ""
    sidecars: List[str] = field(default_factory=list)   # full paths moved along
    size: int = 0
    selected: bool = True
    note: str = ""                    # problem / info text for the UI
    blocked: bool = False             # cannot be moved as configured

    @property
    def filename(self) -> str:
        return os.path.basename(self.source)


def _is_video(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in VIDEO_EXTS


def find_sidecars(parent: str, video_name: str, all_names: List[str]) -> List[str]:
    stem = os.path.splitext(video_name)[0].lower()
    out = []
    for n in all_names:
        low = n.lower()
        if n == video_name or _is_video(n):
            continue
        if low.startswith(stem + ".") and os.path.splitext(low)[1] in SIDECAR_EXTS:
            out.append(os.path.join(parent, n))
    return out


def scan_loose_movies(parent: str) -> Tuple[List[MovieMove], List[Tuple[str, str]]]:
    """Find video files directly inside ``parent``.

    Returns ``(moves, skipped)`` where ``skipped`` is a list of
    ``(file name, reason)`` for files intentionally left alone.
    """
    moves: List[MovieMove] = []
    skipped: List[Tuple[str, str]] = []
    try:
        entries = [e for e in os.scandir(parent) if e.is_file()]
    except OSError:
        return moves, skipped
    names = [e.name for e in entries]

    for e in sorted(entries, key=lambda x: x.name.lower()):
        if not _is_video(e.name):
            continue
        try:
            size = e.stat().st_size
        except OSError:
            size = 0
        if is_tv_episode(e.name):
            skipped.append((e.name, "Looks like a TV episode"))
            continue
        if "sample" in e.name.lower() and size < _SAMPLE_MAX_BYTES:
            skipped.append((e.name, "Looks like a sample clip"))
            continue
        folder, title, year = folder_name_for(e.name)
        move = MovieMove(
            source=e.path, folder_name=folder, title=title, year=year,
            sidecars=find_sidecars(parent, e.name, names), size=size,
        )
        validate(move, parent)
        moves.append(move)
    return moves, skipped


def validate(move: MovieMove, parent: str) -> None:
    """Refresh ``move.note`` / ``move.blocked`` for its current folder name."""
    move.blocked = False
    name = sanitize_folder_name(move.folder_name)
    extra = f"+{len(move.sidecars)} subtitle/info file(s)" if move.sidecars else ""
    if not name:
        move.blocked, move.note = True, "Folder name can't be empty"
        return
    dest_dir = os.path.join(parent, name)
    if os.path.isfile(dest_dir):
        move.blocked, move.note = True, "A file with this name already exists"
        return
    if os.path.isdir(dest_dir):
        files = [move.source, *move.sidecars]
        clash = next((os.path.basename(f) for f in files if os.path.exists(os.path.join(dest_dir, os.path.basename(f)))), None)
        if clash:
            move.blocked, move.note = True, f"'{clash}' already exists in that folder"
            return
        move.note = "Folder exists — will be added to it" + (f"  ·  {extra}" if extra else "")
        return
    move.note = extra


# ── Executing / undoing ───────────────────────────────────────────────

@dataclass
class OrganizeResult:
    folders: List[str] = field(default_factory=list)          # folders now containing the movies
    moved: int = 0
    errors: List[Tuple[str, str]] = field(default_factory=list)  # (file name, message)


def _log_path() -> str:
    return os.path.join(data_dir(), "organize_log.json")


def _load_log() -> List[dict]:
    try:
        with open(_log_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_log(batches: List[dict]) -> None:
    with open(_log_path(), "w", encoding="utf-8") as f:
        json.dump(batches[-20:], f, indent=2)


def execute(moves: List[MovieMove], parent: str) -> OrganizeResult:
    """Move every selected, unblocked movie (and its sidecars) into its folder."""
    result = OrganizeResult()
    records: List[dict] = []

    for mv in moves:
        if not mv.selected or mv.blocked:
            continue
        name = sanitize_folder_name(mv.folder_name)
        dest_dir = os.path.join(parent, name)
        created = not os.path.isdir(dest_dir)
        done: List[Tuple[str, str]] = []
        try:
            os.makedirs(dest_dir, exist_ok=True)
            for src in [mv.source, *mv.sidecars]:
                dst = os.path.join(dest_dir, os.path.basename(src))
                if os.path.exists(dst):
                    raise FileExistsError(f"'{os.path.basename(dst)}' already exists in '{name}'")
                shutil.move(src, dst)
                done.append((src, dst))
        except Exception as exc:
            # Roll this one movie back so a half-finished move never gets left behind.
            for src, dst in reversed(done):
                try:
                    shutil.move(dst, src)
                except OSError:
                    pass
            if created:
                try:
                    os.rmdir(dest_dir)
                except OSError:
                    pass
            result.errors.append((mv.filename, str(exc)))
            continue

        result.moved += 1
        if dest_dir not in result.folders:
            result.folders.append(dest_dir)
        records.append({"folder": dest_dir, "created": created, "files": [[s, d] for s, d in done]})

    if records:
        batches = _load_log()
        batches.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "parent": parent, "records": records})
        _save_log(batches)
    return result


def last_batch_summary() -> Optional[Tuple[str, int]]:
    """``(parent folder, number of movies)`` of the most recent batch, if any."""
    batches = _load_log()
    if not batches:
        return None
    b = batches[-1]
    return b.get("parent", ""), len(b.get("records", []))


def undo_last_batch(undo_icon: Optional[Callable[[str], bool]] = None) -> Tuple[int, List[str]]:
    """Move the files of the most recent batch back where they came from.

    ``undo_icon(folder)`` is called first for each folder so a folder icon that
    was applied afterwards is reverted before the (then empty) folder is removed.
    Returns ``(movies restored, error messages)``.
    """
    batches = _load_log()
    if not batches:
        return 0, ["Nothing to undo."]
    batch = batches[-1]
    restored, errors = 0, []

    for rec in reversed(batch.get("records", [])):
        folder = rec["folder"]
        if undo_icon is not None:
            try:
                undo_icon(folder)
            except Exception:
                pass
        ok = True
        for src, dst in reversed(rec["files"]):
            try:
                if not os.path.exists(dst):
                    continue
                if os.path.exists(src):
                    raise FileExistsError(f"'{os.path.basename(src)}' already exists in the original location")
                shutil.move(dst, src)
            except Exception as exc:
                ok = False
                errors.append(f"{os.path.basename(dst)}: {exc}")
        if ok:
            restored += 1
            if rec.get("created"):
                try:
                    os.rmdir(folder)      # only succeeds if it is empty
                except OSError:
                    pass

    batches.pop()
    _save_log(batches)
    return restored, errors
