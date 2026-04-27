import os
import json
import keyring

APP_NAME = "FolderIconChanger"
_CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
_PREFS_FILE = os.path.join(_CONFIG_DIR, "prefs.json")

_DEFAULTS = {
    "icon_style": "clean_poster",
    "auto_apply_threshold": 85,
    "rounded_corners": True,
    "corner_radius": 12,
    "show_rating_badge": False,
    "upscale_anime": True,
    "icon_size": 256,
    "dark_mode": True,
}


def _ensure_dir():
    os.makedirs(_CONFIG_DIR, exist_ok=True)


def get_api_key(service: str) -> str:
    return keyring.get_password(APP_NAME, service) or ""


def set_api_key(service: str, value: str):
    keyring.set_password(APP_NAME, service, value)


def load_prefs() -> dict:
    _ensure_dir()
    if os.path.exists(_PREFS_FILE):
        try:
            with open(_PREFS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return {**_DEFAULTS, **saved}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save_prefs(prefs: dict):
    _ensure_dir()
    with open(_PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)


def cache_dir() -> str:
    path = os.path.join(_CONFIG_DIR, "cache")
    os.makedirs(path, exist_ok=True)
    return path


def undo_dir() -> str:
    path = os.path.join(_CONFIG_DIR, "undo")
    os.makedirs(path, exist_ok=True)
    return path
