# Suno Chart v1.05 Auth / Playlist Setup

## What changed

v1.05 adds Google/OIDC login and logged-in user features:

- Logged-in users can submit manual Suno song collection requests.
- Logged-in users can create one or more saved playlists.
- Playlists are stored per user on the `data` branch as JSON files under `data/user_playlists/`.
- Playlists already include a `visibility` field (`private` / `public`) so public sharing can be expanded later.

## Required Streamlit version

`requirements.txt` now uses:

```txt
streamlit>=1.42.0
Authlib>=1.3.2
```

## Required secrets

Add these to Streamlit Cloud Secrets or local `.streamlit/secrets.toml`.
Use `.streamlit/secrets.example.toml` as a template.

```toml
DATA_ZIP_PASSWORD = "..."
DATA_RAW_BASE_URL = "https://raw.githubusercontent.com/Busy-studio/sunotrending/data/data"
GITHUB_ACTION_TOKEN = "..."
APP_PUBLIC_BASE_URL = "https://your-streamlit-app-url"

[auth]
redirect_uri = "https://your-streamlit-app-url/oauth2callback"
cookie_secret = "a-long-random-secret"

[auth.google]
client_id = "..."
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

## Google OAuth setup

In Google Cloud Console, create an OAuth client for a web application and add this redirect URI:

```txt
https://your-streamlit-app-url/oauth2callback
```

For local testing, also add:

```txt
http://localhost:8501/oauth2callback
```

## GitHub token permissions

`GITHUB_ACTION_TOKEN` needs repository Contents read/write permission because the app writes:

- `data/manual_song_queue.csv`
- `data/user_playlists/<user_key>.json`

## Current limitation

The existing HTML audio player playlist is still a browser-side runtime playlist.
The saved playlist feature is server-side and lets users create playlists and add songs from the current payload charts.
A later version can wire the HTML player's current queue directly into saved playlists using a custom Streamlit component bridge.
