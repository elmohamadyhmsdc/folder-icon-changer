import requests
from typing import List, Optional

_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_BASE = "https://api.igdb.com/v4"
_IMAGE_BASE = "https://images.igdb.com/igdb/image/upload/t_1080p/{image_id}.jpg"
_COVER_BASE = "https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"

_cached_token: Optional[str] = None


def _get_token(client_id: str, client_secret: str) -> Optional[str]:
    global _cached_token
    if _cached_token:
        return _cached_token
    try:
        resp = requests.post(
            _TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        resp.raise_for_status()
        _cached_token = resp.json().get("access_token")
        return _cached_token
    except Exception:
        return None


def search(title: str, client_id: str, client_secret: str, limit: int = 10) -> List[dict]:
    token = _get_token(client_id, client_secret)
    if not token:
        return []
    try:
        resp = requests.post(
            f"{_BASE}/games",
            headers={"Client-ID": client_id, "Authorization": f"Bearer {token}"},
            data=f'search "{title}"; fields name,cover.image_id,rating,summary,first_release_date; limit {limit};',
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def cover_url(entry: dict) -> Optional[str]:
    cover = entry.get("cover") or {}
    image_id = cover.get("image_id")
    if not image_id:
        return None
    return _IMAGE_BASE.format(image_id=image_id)


def display_title(entry: dict) -> str:
    return entry.get("name") or ""


def rating(entry: dict) -> Optional[float]:
    r = entry.get("rating")
    return round(float(r) / 10, 1) if r else None
