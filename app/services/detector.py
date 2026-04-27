import re
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ContentType(str, Enum):
    ANIME = "Anime"
    MOVIE = "Movie"
    TV = "TV Show"
    GAME = "Game"
    UNKNOWN = "Unknown"


@dataclass
class DetectionResult:
    content_type: ContentType
    confidence: float  # 0.0–1.0
    clean_title: str


_ANIME_PATTERNS = [
    r"\[[\w\s\-\.]+\]",              # [SubGroup] tag
    r"[぀-ヿ一-鿿]", # Japanese/Chinese characters
    r"\b(S\d{1,2}|Season\s*\d+)\b.{0,10}\b(E\d{2})\b",  # SxxExx short title
    r"\b(OVA|ONA|OAV|Specials?)\b",
    r"\b(Dubbed|Subbed|Dual\s*Audio)\b",
    r"\bBD(?:Rip)?\b",              # BDRip common in anime releases
]

_MOVIE_PATTERNS = [
    r"\b(19|20)\d{2}\b",            # year anywhere
    r"\b(BluRay|BDRip|WEB-DL|WEBRip|HDTV|DVDRip)\b",
    r"\b(Directors?\.?Cut|Extended|Theatrical|Unrated|Remastered)\b",
    r"\b(1080p|2160p|4K|UHD)\b",
]

_TV_PATTERNS = [
    r"\bSeason\s*\d+\b",
    r"\bS\d{2}E\d{2}\b",
    r"\bS\d{2}\b",               # "S03" alone — season pack
    r"\bComplete(?:\s*Series)?\b",
    r"\bEpisode\s*\d+\b",
]

_GAME_PATTERNS = [
    r"\b(CODEX|SKIDROW|FitGirl|EMPRESS|PLAZA|CPY|RELOADED|P2P|TiNYiSO|RePack)\b",
    r"\b(PC\s*Game|Steam|GOG|Epic\s*Games)\b",
    r"\b(v\d+\.\d+|Update\s*\d+|DLC|GOTY|Definitive\s*Edition)\b",
]


def _count_pattern_hits(name: str, patterns: list) -> int:
    hits = 0
    for pat in patterns:
        if re.search(pat, name, re.IGNORECASE):
            hits += 1
    return hits


def _clean_title(name: str) -> str:
    cleaned = re.sub(r"\[.*?\]|\(.*?\)", " ", name)
    cleaned = re.sub(
        r"\b(BluRay|BDRip|WEBRip|WEB-DL|HDTV|DVDRip|HEVC|x264|x265|H\.264|H\.265|"
        r"AVC|AAC|AC3|DTS|FLAC|480p|720p|1080p|2160p|4K|UHD|HDR|SDR)\b",
        " ", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(19|20)\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"[-_\.]+", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def detect(folder_name: str, scan_contents: bool = False, folder_path: Optional[str] = None) -> DetectionResult:
    name = os.path.basename(folder_name)
    scores = {
        ContentType.ANIME: _count_pattern_hits(name, _ANIME_PATTERNS),
        ContentType.MOVIE: _count_pattern_hits(name, _MOVIE_PATTERNS),
        ContentType.TV: _count_pattern_hits(name, _TV_PATTERNS),
        ContentType.GAME: _count_pattern_hits(name, _GAME_PATTERNS),
    }

    if scan_contents and folder_path and os.path.isdir(folder_path):
        ext_counts = {"mkv": 0, "mp4": 0, "avi": 0, "exe": 0, "iso": 0}
        try:
            for entry in os.scandir(folder_path):
                ext = entry.name.rsplit(".", 1)[-1].lower()
                if ext in ext_counts:
                    ext_counts[ext] += 1
        except PermissionError:
            pass

        if ext_counts["exe"] + ext_counts["iso"] > 0:
            scores[ContentType.GAME] += 2
        if ext_counts["mkv"] > 3:
            scores[ContentType.ANIME] += 1  # MKV common in anime batches

    best_type = max(scores, key=lambda t: scores[t])
    best_score = scores[best_type]
    total = sum(scores.values()) or 1

    if best_score == 0:
        return DetectionResult(ContentType.UNKNOWN, 0.0, _clean_title(name))

    confidence = min(1.0, best_score / max(2, total) + 0.3)
    return DetectionResult(best_type, round(confidence, 2), _clean_title(name))
