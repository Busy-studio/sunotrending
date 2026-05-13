"""Supabase helpers for Suno Chart user features.

This module is intentionally server-side only. It reads the Supabase service role
key from Streamlit secrets and never exposes it to the HTML/JS player component.

Phase 1 scope:
- Connect to Supabase.
- Save the logged-in Google/Streamlit user into public.user_profiles.
- Provide helper functions for playlists, likes, and app stats for the next UI steps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import streamlit as st

try:
    from supabase import Client, create_client
except Exception:  # pragma: no cover - handled at runtime in Streamlit
    Client = Any  # type: ignore
    create_client = None  # type: ignore


@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Optional[Client]:
    """Return a cached Supabase client, or None when secrets/package are missing."""
    if create_client is None:
        return None

    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key:
        return None

    try:
        return create_client(str(url), str(key))
    except Exception:
        return None


def is_supabase_configured() -> bool:
    return bool(st.secrets.get("SUPABASE_URL", "")) and bool(
        st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
    )


def is_login_available() -> bool:
    """Best-effort check for Streamlit OIDC availability."""
    return hasattr(st, "login") and hasattr(st, "user")


def is_logged_in() -> bool:
    user = getattr(st, "user", None)
    return bool(user is not None and getattr(user, "is_logged_in", False))


def _user_get(key: str, default: str = "") -> str:
    user = getattr(st, "user", None)
    if not user:
        return default

    try:
        value = user.get(key, default)
    except Exception:
        value = getattr(user, key, default)

    if value is None:
        return default
    return str(value)


def get_current_user_profile() -> Optional[Dict[str, str]]:
    """Return the logged-in user's profile in a DB-friendly shape."""
    if not is_logged_in():
        return None

    # Google OIDC normally provides sub, email, name, picture.
    # sub is stable and should be preferred over email as the internal user_id.
    user_id = _user_get("sub") or _user_get("email")
    if not user_id:
        return None

    return {
        "user_id": user_id,
        "email": _user_get("email"),
        "name": _user_get("name"),
        "picture": _user_get("picture"),
    }


def get_current_user_id() -> Optional[str]:
    profile = get_current_user_profile()
    return profile["user_id"] if profile else None


def upsert_user_profile() -> bool:
    """Create/update public.user_profiles for the current logged-in user."""
    sb = get_supabase_client()
    profile = get_current_user_profile()
    if not sb or not profile:
        return False

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        **profile,
        "last_login_at": now,
    }

    try:
        # created_at remains DB default on first insert. On conflict, profile fields update.
        sb.table("user_profiles").upsert(payload, on_conflict="user_id").execute()
        return True
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return False


def list_playlists(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    user_id = user_id or get_current_user_id()
    if not sb or not user_id:
        return []

    try:
        result = (
            sb.table("playlists")
            .select("id, name, visibility, created_at, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return []


def create_playlist(name: str, song_ids: Iterable[str], user_id: Optional[str] = None) -> Optional[str]:
    """Create a playlist with ordered song IDs. Returns playlist_id when successful."""
    sb = get_supabase_client()
    user_id = user_id or get_current_user_id()
    clean_song_ids = [str(song_id).strip() for song_id in song_ids if str(song_id).strip()]

    if not sb or not user_id:
        return None

    try:
        playlist_result = (
            sb.table("playlists")
            .insert({"user_id": user_id, "name": name or "My Playlist", "visibility": "private"})
            .execute()
        )
        playlist_id = playlist_result.data[0]["id"]

        rows = [
            {"playlist_id": playlist_id, "song_id": song_id, "position": idx}
            for idx, song_id in enumerate(clean_song_ids)
        ]
        if rows:
            sb.table("playlist_items").insert(rows).execute()

        return playlist_id
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return None


def get_playlist_items(playlist_id: str, user_id: Optional[str] = None) -> List[str]:
    """Return song IDs for a playlist owned by user_id."""
    sb = get_supabase_client()
    user_id = user_id or get_current_user_id()
    if not sb or not user_id or not playlist_id:
        return []

    try:
        owned = (
            sb.table("playlists")
            .select("id")
            .eq("id", playlist_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not owned.data:
            return []

        result = (
            sb.table("playlist_items")
            .select("song_id, position")
            .eq("playlist_id", playlist_id)
            .order("position")
            .execute()
        )
        return [str(row["song_id"]) for row in result.data or []]
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return []


def delete_playlist(playlist_id: str, user_id: Optional[str] = None) -> bool:
    sb = get_supabase_client()
    user_id = user_id or get_current_user_id()
    if not sb or not user_id or not playlist_id:
        return False

    try:
        sb.table("playlists").delete().eq("id", playlist_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return False


def get_app_song_stats() -> Dict[str, Dict[str, Any]]:
    """Return aggregated app-side play/like stats keyed by song_id."""
    sb = get_supabase_client()
    if not sb:
        return {}

    try:
        result = sb.table("app_song_stats").select("*").execute()
        return {str(row["song_id"]): row for row in result.data or []}
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return {}


def toggle_like(song_id: str, user_id: Optional[str] = None) -> Optional[bool]:
    """Toggle a like for the current user. Returns True when liked, False when unliked."""
    sb = get_supabase_client()
    user_id = user_id or get_current_user_id()
    song_id = str(song_id).strip()
    if not sb or not user_id or not song_id:
        return None

    try:
        existing = (
            sb.table("app_likes")
            .select("user_id")
            .eq("user_id", user_id)
            .eq("song_id", song_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            sb.table("app_likes").delete().eq("user_id", user_id).eq("song_id", song_id).execute()
            liked = False
        else:
            sb.table("app_likes").insert({"user_id": user_id, "song_id": song_id}).execute()
            liked = True

        refresh_song_stats(song_id)
        return liked
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return None


def record_play_event(
    song_id: str,
    play_seconds: int = 0,
    counted: bool = False,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> bool:
    sb = get_supabase_client()
    user_id = user_id or get_current_user_id()
    song_id = str(song_id).strip()
    if not sb or not song_id:
        return False

    try:
        sb.table("app_play_events").insert(
            {
                "user_id": user_id,
                "song_id": song_id,
                "session_id": session_id,
                "play_seconds": int(play_seconds or 0),
                "counted": bool(counted),
            }
        ).execute()
        if counted:
            refresh_song_stats(song_id)
        return True
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return False


def refresh_song_stats(song_id: str) -> bool:
    """Refresh aggregate stats for one song.

    This is fine for early-stage traffic. Later, move aggregation to SQL RPC/trigger
    if app traffic grows.
    """
    sb = get_supabase_client()
    song_id = str(song_id).strip()
    if not sb or not song_id:
        return False

    try:
        like_result = (
            sb.table("app_likes")
            .select("song_id", count="exact")
            .eq("song_id", song_id)
            .execute()
        )
        play_result = (
            sb.table("app_play_events")
            .select("song_id", count="exact")
            .eq("song_id", song_id)
            .eq("counted", True)
            .execute()
        )
        listener_result = (
            sb.table("app_play_events")
            .select("user_id")
            .eq("song_id", song_id)
            .eq("counted", True)
            .execute()
        )
        unique_users = {
            row.get("user_id")
            for row in listener_result.data or []
            if row.get("user_id")
        }

        sb.table("app_song_stats").upsert(
            {
                "song_id": song_id,
                "app_like_count": like_result.count or 0,
                "app_play_count": play_result.count or 0,
                "unique_listener_count": len(unique_users),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="song_id",
        ).execute()
        return True
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return False

# ================================
# Browser-side playlist RPC support
# ================================

def get_supabase_public_config() -> Dict[str, str]:
    """Return browser-safe Supabase config for the JS player.

    SUPABASE_ANON_KEY is safe to expose in browser code when paired with RLS/RPC.
    The service role key is never exposed.
    """
    return {
        "supabase_url": str(st.secrets.get("SUPABASE_URL", "") or ""),
        "supabase_anon_key": str(st.secrets.get("SUPABASE_ANON_KEY", "") or ""),
    }


def ensure_playlist_cloud_token() -> str:
    """Create/read a per-user random token used by browser RPC playlist calls.

    Requires the SQL migration in supabase/playlist_rpc.sql.
    Returns an empty string when the column/migration has not been applied yet.
    """
    import secrets

    sb = get_supabase_client()
    profile = get_current_user_profile()
    if not sb or not profile:
        return ""

    user_id = profile["user_id"]
    try:
        existing = (
            sb.table("user_profiles")
            .select("playlist_cloud_token")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            token = str((existing.data[0] or {}).get("playlist_cloud_token") or "")
            if token:
                return token

        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            **profile,
            "playlist_cloud_token": token,
            "last_login_at": now,
        }
        sb.table("user_profiles").upsert(payload, on_conflict="user_id").execute()
        return token
    except Exception as exc:
        st.session_state["supabase_last_error"] = str(exc)
        return ""
