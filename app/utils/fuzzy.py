import re
from typing import List, Tuple, Any

from rapidfuzz import fuzz, process

# Tokens that appear in folder names but not in media titles
_NOISE_PATTERNS = [
    r"\[.*?\]",                          # [SubGroup], [1080p], [BluRay]
    r"\(.*?\)",                          # (2024), (Director's Cut)
    r"\b(19|20)\d{2}\b",                # standalone years
    r"\b(480|720|1080|2160)[pi]?\b",    # resolutions
    r"\b(BluRay|BDRip|WEBRip|WEB-DL|HDTV|DVDRip|HEVC|x264|x265|H\.264|H\.265|AVC|AAC|AC3|DTS|FLAC)\b",
    r"\b(PROPER|REPACK|EXTENDED|THEATRICAL|UNRATED|DIRECTORS\.CUT)\b",
    r"\b(Season|S\d{1,2}|E\d{1,2}|Complete|Part\s*\d+)\b",
    r"[-_\.]+",                          # separators
]

_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)


def clean_title(name: str) -> str:
    """Strip noise from a folder name to get a clean search title."""
    cleaned = _NOISE_RE.sub(" ", name)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def best_match(query: str, candidates: List[dict], title_keys: List[str], top_n: int = 5) -> List[Tuple[dict, float]]:
    """
    Find the best matching candidates for a query string.

    candidates: list of result dicts from an API
    title_keys: ordered list of keys to try for the title field (e.g. ['title_english', 'title_romaji'])
    Returns list of (candidate, score 0-100) sorted descending.
    """
    if not candidates:
        return []

    def get_title(c: dict) -> str:
        for key in title_keys:
            parts = key.split(".")
            val = c
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p, "")
                else:
                    val = ""
                    break
            if val:
                return str(val)
        return ""

    labeled = [(get_title(c), c) for c in candidates]
    titles = [t for t, _ in labeled]

    results = process.extract(query, titles, scorer=fuzz.token_sort_ratio, limit=top_n)
    ranked = []
    for title, score, idx in results:
        ranked.append((candidates[idx], float(score)))

    return ranked
