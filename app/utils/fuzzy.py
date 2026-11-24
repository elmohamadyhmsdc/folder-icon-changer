import re
from typing import Any, List, Tuple

from rapidfuzz import fuzz

# Tokens that appear in folder names but not in media titles.
# NOTE: years are handled separately (see _strip_trailing_year) so that titles
# such as "1917" or "2001 A Space Odyssey" are not destroyed.
_NOISE_PATTERNS = [
    r"\[.*?\]",                          # [SubGroup], [1080p], [BluRay]
    r"\(.*?\)",                          # (2024), (Director's Cut)
    r"\b(480|720|1080|2160)[pi]?\b",    # resolutions
    r"\b(BluRay|BDRip|WEBRip|WEB-DL|HDTV|DVDRip|HEVC|x264|x265|H\.264|H\.265|AVC|AAC|AC3|DTS|FLAC)\b",
    r"\b(PROPER|REPACK|EXTENDED|THEATRICAL|UNRATED|DIRECTORS\.CUT)\b",
    r"\b(Season|S\d{1,2}|E\d{1,2}|Complete|Part\s*\d+)\b",
    r"[-_\.]+",                          # separators
]

_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

# A release year (1900–2029) at the very end of the name, e.g. "Inception 2010".
# 2030+ is deliberately excluded so "Blade Runner 2049" keeps its number.
_TRAILING_YEAR_RE = re.compile(r"\s+(?:19\d{2}|20[0-2]\d)$")


def clean_title(name: str) -> str:
    """Strip noise from a folder name to get a clean search title."""
    cleaned = _NOISE_RE.sub(" ", name)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # Only drop a trailing year when something else remains, so a title that
    # *is* a year ("1917", "2012") is kept.
    stripped = _TRAILING_YEAR_RE.sub("", cleaned).strip()
    if stripped:
        cleaned = stripped
    # Fall back to the raw name rather than searching for an empty string.
    return cleaned or name.strip()


def _titles_for(candidate: dict, title_keys: List[str]) -> List[str]:
    """Return every non-empty title found under title_keys (dotted paths allowed)."""
    titles: List[str] = []
    for key in title_keys:
        val: Any = candidate
        for part in key.split("."):
            if isinstance(val, dict):
                val = val.get(part, "")
            else:
                val = ""
                break
        if val:
            titles.append(str(val))
    return titles


def best_match(query: str, candidates: List[dict], title_keys: List[str], top_n: int = 5) -> List[Tuple[dict, float]]:
    """
    Find the best matching candidates for a query string.

    candidates: list of result dicts from an API
    title_keys: keys holding alternative titles (e.g. ['title.english', 'title.romaji']).
                A candidate is scored against *all* of them and keeps its best score,
                so a folder named after the romaji title still matches a result that
                also has an English title.
    Returns list of (candidate, score 0-100) sorted descending.
    """
    if not candidates:
        return []

    scored: List[Tuple[dict, float]] = []
    for cand in candidates:
        titles = _titles_for(cand, title_keys)
        score = max((fuzz.token_sort_ratio(query, t) for t in titles), default=0.0)
        scored.append((cand, float(score)))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_n]
