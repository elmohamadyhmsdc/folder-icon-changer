from dataclasses import dataclass, field
from typing import List, Optional

from app.api import anilist, jikan, tmdb, igdb
from app.config import get_api_key
from app.services.detector import ContentType
from app.utils import cache as _cache
from app.utils.fuzzy import clean_title, best_match


@dataclass
class SearchResult:
    title: str
    year: str
    score: Optional[float]          # numeric rating (e.g. 8.7)
    image_url: Optional[str]
    source: str                     # "anilist", "jikan", "tmdb_movie", "tmdb_tv", "igdb"
    confidence: float               # fuzzy match confidence 0-100
    raw: dict = field(default_factory=dict)


def _anilist_to_result(entry: dict, confidence: float) -> SearchResult:
    title_en = (entry.get("title") or {}).get("english") or ""
    title_ro = (entry.get("title") or {}).get("romaji") or ""
    score_val = entry.get("averageScore")
    return SearchResult(
        title=title_en or title_ro,
        year=str(entry.get("seasonYear") or ""),
        score=round(score_val / 10, 1) if score_val else None,
        image_url=anilist.best_image_url(entry),
        source="anilist",
        confidence=confidence,
        raw=entry,
    )


def _jikan_to_result(entry: dict, confidence: float) -> SearchResult:
    return SearchResult(
        title=jikan.title_english(entry) or jikan.title_romaji(entry),
        year=str((entry.get("aired") or {}).get("prop", {}).get("from", {}).get("year") or ""),
        score=jikan.score(entry),
        image_url=jikan.best_image_url(entry),
        source="jikan",
        confidence=confidence,
        raw=entry,
    )


def _tmdb_to_result(entry: dict, confidence: float, kind: str) -> SearchResult:
    return SearchResult(
        title=tmdb.display_title(entry),
        year=tmdb.year(entry),
        score=tmdb.vote_average(entry),
        image_url=tmdb.poster_url(entry),
        source=kind,
        confidence=confidence,
        raw=entry,
    )


def _igdb_to_result(entry: dict, confidence: float) -> SearchResult:
    return SearchResult(
        title=igdb.display_title(entry),
        year="",
        score=igdb.rating(entry),
        image_url=igdb.cover_url(entry),
        source="igdb",
        confidence=confidence,
        raw=entry,
    )


def search_anime(query: str) -> List[SearchResult]:
    clean = clean_title(query)
    cache_key = _cache.api_key(clean, "anilist")
    cached = _cache.get(cache_key)

    if cached is None:
        results = anilist.search(clean)
        _cache.set(cache_key, results, ttl=86400)
    else:
        results = cached

    if not results:
        # Fallback to Jikan
        jikan_key = _cache.api_key(clean, "jikan")
        jikan_cached = _cache.get(jikan_key)
        if jikan_cached is None:
            results = jikan.search(clean)
            _cache.set(jikan_key, results, ttl=86400)
        else:
            results = jikan_cached

        ranked = best_match(clean, results, ["title_english", "title"], top_n=5)
        return [_jikan_to_result(entry, conf) for entry, conf in ranked]

    ranked = best_match(clean, results, ["title.english", "title.romaji"], top_n=5)
    return [_anilist_to_result(entry, conf) for entry, conf in ranked]


def search_movie(query: str) -> List[SearchResult]:
    key = get_api_key("tmdb")
    if not key:
        return []
    clean = clean_title(query)
    cache_key = _cache.api_key(clean, "tmdb_movie")
    cached = _cache.get(cache_key)
    if cached is None:
        results = tmdb.search_movie(clean, key)
        _cache.set(cache_key, results, ttl=86400)
    else:
        results = cached
    ranked = best_match(clean, results, ["title"], top_n=5)
    return [_tmdb_to_result(e, c, "tmdb_movie") for e, c in ranked]


def search_tv(query: str) -> List[SearchResult]:
    key = get_api_key("tmdb")
    if not key:
        return []
    clean = clean_title(query)
    cache_key = _cache.api_key(clean, "tmdb_tv")
    cached = _cache.get(cache_key)
    if cached is None:
        results = tmdb.search_tv(clean, key)
        _cache.set(cache_key, results, ttl=86400)
    else:
        results = cached
    ranked = best_match(clean, results, ["name"], top_n=5)
    return [_tmdb_to_result(e, c, "tmdb_tv") for e, c in ranked]


def search_game(query: str) -> List[SearchResult]:
    client_id = get_api_key("igdb_client_id")
    client_secret = get_api_key("igdb_client_secret")
    if not client_id or not client_secret:
        return []
    clean = clean_title(query)
    cache_key = _cache.api_key(clean, "igdb")
    cached = _cache.get(cache_key)
    if cached is None:
        results = igdb.search(clean, client_id, client_secret)
        _cache.set(cache_key, results, ttl=86400)
    else:
        results = cached
    ranked = best_match(clean, results, ["name"], top_n=5)
    return [_igdb_to_result(e, c) for e, c in ranked]


def search_for(folder_name: str, content_type: ContentType) -> List[SearchResult]:
    if content_type == ContentType.ANIME:
        return search_anime(folder_name)
    elif content_type == ContentType.MOVIE:
        return search_movie(folder_name)
    elif content_type == ContentType.TV:
        return search_tv(folder_name)
    elif content_type == ContentType.GAME:
        return search_game(folder_name)
    else:
        # Unknown: try all sources, merge and sort by confidence
        all_results = (
            search_anime(folder_name)
            + search_movie(folder_name)
            + search_tv(folder_name)
            + search_game(folder_name)
        )
        return sorted(all_results, key=lambda r: r.confidence, reverse=True)[:10]
