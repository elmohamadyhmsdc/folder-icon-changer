# Folder Icon Changer

A **Windows** desktop app that sets custom **folder icons** from movie, TV, game, and anime artwork. It guesses what each folder name refers to, searches online databases, and applies a generated `.ico` using a `desktop.ini` (the standard Windows approach).

## Requirements

- **Windows** (the icon applier uses Explorer `desktop.ini` and Win32 attributes).
- **Python 3.10+** (recommended).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

From the project root:

```bash
python -m app.main
```

## API keys (optional but recommended)

Open **Settings** in the app to store keys in the system **keyring** (not in plain project files).

| Service | Use |
|--------|-----|
| **TMDB** | Movies and TV (get a key at [themoviedb.org](https://www.themoviedb.org/)). |
| **IGDB** | Games (Twitch [developer](https://dev.twitch.tv/) client ID and secret). |
| **AniList** | Anime — no API key. |

Jikan (MyAnimeList) is also used for anime without extra keys, depending on search results.

## Data and config

- **Preferences:** `%APPDATA%\FolderIconChanger\prefs.json`
- **Cache and undo** live under the same `FolderIconChanger` app data directory.

## Tech stack

- **PyQt6** — UI
- **requests**, **gql** — HTTP / GraphQL APIs
- **Pillow** — image / ICO building
- **rapidfuzz** — name matching
- **diskcache**, **keyring**, **python-dotenv** — cache, secrets, env

## License

Add a license file if you distribute this project.
