# Suno Chart Google Auth setup

This build keeps the v1.04.3 chart renderer intact and adds only minimal Google login gating.

Required Streamlit secrets:

```toml
DATA_ZIP_PASSWORD = "..."
GITHUB_ACTION_TOKEN = "github_pat_..."
GITHUB_REPO_OWNER = "Busy-studio"
GITHUB_REPO_NAME = "sunotrending"

[auth]
redirect_uri = "https://sunotrending.streamlit.app/oauth2callback"
cookie_secret = "GENERATE_A_LONG_RANDOM_STRING"

[auth.google]
client_id = "YOUR_CLIENT_ID.apps.googleusercontent.com"
client_secret = "YOUR_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Google OAuth client type: Web application.
Authorized redirect URI:

```text
https://sunotrending.streamlit.app/oauth2callback
```
