import requests
from typing import List, Optional

BASE = "https://api.jikan.moe/v4"


def search(title: str, limit: int = 10) -> List[dict]:
    """Search MyAnimeList via Jikan. Returns list of anime dicts."""
    try:
        resp = requests.get(
            f"{BASE}/anime",
            params={"q": title, "limit": limit, "order_by": "score", "sort": "desc"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception:
        return []


def best_image_url(entry: dict) -> Optional[str]:
    """Return the best available image URL from a Jikan anime dict."""
    images = entry.get("images") or {}
    jpg = images.get("jpg") or {}
    return jpg.get("large_image_url") or jpg.get("image_url")


def title_english(entry: dict) -> str:
    return entry.get("title_english") or entry.get("title") or ""


def title_romaji(entry: dict) -> str:
    return entry.get("title") or ""


def score(entry: dict) -> Optional[float]:
    s = entry.get("score")
    return float(s) if s else None
