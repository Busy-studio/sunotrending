# Auth Troubleshooting

## Google Cloud Console

Authorized JavaScript origins:

```text
https://sunotrending.streamlit.app
```

Authorized redirect URIs:

```text
https://sunotrending.streamlit.app/oauth2callback
https://sunotrending.streamlit.app/~/+/oauth2callback
```

## Streamlit Secrets

Keep `redirect_uri` on the official Streamlit callback path:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "YOUR_SUPABASE_SECRET_KEY"

[auth]
redirect_uri = "https://sunotrending.streamlit.app/oauth2callback"
cookie_secret = "A_RANDOM_32+_CHARACTER_SECRET"
client_id = "YOUR_GOOGLE_WEB_CLIENT_ID"
client_secret = "YOUR_GOOGLE_WEB_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

## Why Streamlit is pinned

`requirements.txt` pins Streamlit to `1.56.0` because `1.57.0` has reported OAuth callback state/cookie regression symptoms. Do not change back to `streamlit>=1.42.0` until the OAuth callback is confirmed stable.

## Browser test

After changing secrets or Google OAuth settings:

1. Save Google Cloud Console settings.
2. Save Streamlit Secrets.
3. Reboot the Streamlit app.
4. Test in an incognito/private window.
