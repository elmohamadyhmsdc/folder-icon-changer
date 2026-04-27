import requests
from typing import List, Optional

BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/original"


def _get(endpoint: str, api_key: str, **params) -> dict:
    try:
        resp = requests.get(
            f"{BASE}{endpoint}",
            params={"api_key": api_key, **params},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def search_movie(title: str, api_key: str) -> List[dict]:
    data = _get("/search/movie", api_key, query=title, include_adult=False)
    return data.get("results", [])


def search_tv(title: str, api_key: str) -> List[dict]:
    data = _get("/search/tv", api_key, query=title)
    return data.get("results", [])


def poster_url(entry: dict) -> Optional[str]:
    path = entry.get("poster_path")
    return f"{IMAGE_BASE}{path}" if path else None


def display_title(entry: dict) -> str:
    return entry.get("title") or entry.get("name") or ""


def year(entry: dict) -> str:
    date = entry.get("release_date") or entry.get("first_air_date") or ""
    return date[:4] if date else ""


def vote_average(entry: dict) -> Optional[float]:
    v = entry.get("vote_average")
    return float(v) if v else None
