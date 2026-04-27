import requests
from typing import List, Optional

ENDPOINT = "https://graphql.anilist.co"

_SEARCH_QUERY = """
query SearchAnime($search: String, $perPage: Int) {
  Page(perPage: $perPage) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      id
      title { romaji english native }
      coverImage { extraLarge large medium }
      bannerImage
      averageScore
      episodes
      status
      season
      seasonYear
      genres
      description(asHtml: false)
    }
  }
}
"""

_ID_QUERY = """
query GetAnime($id: Int) {
  Media(id: $id, type: ANIME) {
    id
    title { romaji english native }
    coverImage { extraLarge large medium }
    bannerImage
    averageScore
    episodes
    status
    season
    seasonYear
    genres
    description(asHtml: false)
  }
}
"""


def search(title: str, per_page: int = 10) -> List[dict]:
    """Search AniList for anime by title. Returns list of media dicts."""
    payload = {
        "query": _SEARCH_QUERY,
        "variables": {"search": title, "perPage": per_page},
    }
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("Page", {}).get("media", [])
    except Exception:
        return []


def get_by_id(media_id: int) -> Optional[dict]:
    payload = {
        "query": _ID_QUERY,
        "variables": {"id": media_id},
    }
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", {}).get("Media")
    except Exception:
        return None


def best_image_url(media: dict) -> Optional[str]:
    """Return the highest-quality cover image URL from an AniList media dict."""
    cover = media.get("coverImage") or {}
    return cover.get("extraLarge") or cover.get("large") or cover.get("medium")
