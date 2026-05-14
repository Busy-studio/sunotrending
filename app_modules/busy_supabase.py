from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

try:
    from supabase import create_client
except Exception:
    create_client = None

AUDIO_BUCKET = "busy-audio"
COVER_BUCKET = "busy-cover"
AVATAR_BUCKET = "busy-avatar"

BAD_WORDS = {
    "fuck", "shit", "bitch", "asshole", "cunt", "nigger", "nigga", "faggot",
    "씨발", "시발", "ㅅㅂ", "개새끼", "병신", "ㅂㅅ", "좆", "존나", "꺼져",
}

AUDIO_EXTS = {"mp3"}
COVER_EXTS = {"jpg", "jpeg", "png", "webp"}
AVATAR_EXTS = {"jpg", "jpeg", "png", "webp"}
MAX_AUDIO_MB = 25
MAX_COVER_MB = 6
MAX_AVATAR_MB = 4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@st.cache_resource(show_spinner=False)
def get_supabase_client():
    if create_client is None:
        return None
    url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    if not url or not key:
        return None
    try:
        return create_client(str(url), str(key))
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return None


def get_public_config() -> Dict[str, str]:
    return {
        "supabase_url": str(st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", "")) or ""),
        "supabase_anon_key": str(st.secrets.get("SUPABASE_ANON_KEY", os.getenv("SUPABASE_ANON_KEY", "")) or ""),
    }


def is_supabase_ready() -> bool:
    return bool(get_supabase_client())


def is_login_available() -> bool:
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
    return default if value is None else str(value)


def get_auth_user() -> Optional[Dict[str, str]]:
    if not is_logged_in():
        return None
    user_id = _user_get("sub") or _user_get("email")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "email": _user_get("email"),
        "name": _user_get("name"),
        "picture": _user_get("picture"),
    }


def get_user_id() -> Optional[str]:
    u = get_auth_user()
    return u["user_id"] if u else None


def get_session_id() -> str:
    if "busy_session_id" not in st.session_state:
        st.session_state["busy_session_id"] = str(uuid.uuid4())
    return st.session_state["busy_session_id"]


def actor_key() -> str:
    uid = get_user_id()
    if uid:
        return f"user:{uid}"
    return f"anon:{get_session_id()}"


def clean_text(value: Any, max_len: int = 10000) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "").strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def has_bad_words(text: str) -> bool:
    lowered = (text or "").lower().replace(" ", "")
    return any(word in lowered for word in BAD_WORDS)


def validate_upload_file(file, allowed_exts: set[str], max_mb: int, label: str) -> Tuple[bool, str, str]:
    if not file:
        return False, f"{label} 파일이 필요합니다.", ""
    name = getattr(file, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed_exts:
        return False, f"{label} 파일 형식은 {', '.join(sorted(allowed_exts))}만 가능합니다.", ext
    size = getattr(file, "size", 0) or 0
    if size > max_mb * 1024 * 1024:
        return False, f"{label} 파일은 최대 {max_mb}MB까지 가능합니다.", ext
    return True, "", ext


def public_url(bucket: str, path: str) -> str:
    sb = get_supabase_client()
    if not sb or not path:
        return ""
    try:
        res = sb.storage.from_(bucket).get_public_url(path)
        if isinstance(res, str):
            return res
        return str(res)
    except Exception:
        url = str(st.secrets.get("SUPABASE_URL", "")).rstrip("/")
        return f"{url}/storage/v1/object/public/{bucket}/{path}" if url else ""


def upload_to_bucket(bucket: str, file, folder: str, ext: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    sb = get_supabase_client()
    if not sb or not file:
        return None, None, "Supabase 연결을 확인하세요."
    file_id = str(uuid.uuid4())
    path = f"{folder}/{file_id}.{ext}"
    try:
        data = file.getvalue()
        content_type = getattr(file, "type", None) or "application/octet-stream"
        try:
            sb.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": "true"})
        except TypeError:
            sb.storage.from_(bucket).upload(path, data)
        return path, public_url(bucket, path), None
    except Exception as exc:
        return None, None, str(exc)


def delete_storage_path(bucket: str, path: str) -> None:
    sb = get_supabase_client()
    if not sb or not path:
        return
    try:
        sb.storage.from_(bucket).remove([path])
    except Exception:
        pass


def ensure_profile() -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    auth = get_auth_user()
    if not sb or not auth:
        return None
    try:
        existing = sb.table("bc_profiles").select("*").eq("user_id", auth["user_id"]).limit(1).execute()
        if existing.data:
            row = existing.data[0]
            updates = {"email": auth.get("email"), "last_login_at": now_iso()}
            sb.table("bc_profiles").update(updates).eq("user_id", auth["user_id"]).execute()
            row.update(updates)
            return row
        row = {
            "user_id": auth["user_id"],
            "email": auth.get("email"),
            "display_name": auth.get("name") or auth.get("email") or "Busy User",
            "avatar_url": auth.get("picture"),
            "created_at": now_iso(),
            "last_login_at": now_iso(),
        }
        sb.table("bc_profiles").insert(row).execute()
        return row
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return None


def normalize_url(value: str, max_len: int = 500) -> str:
    value = clean_text(value, max_len)
    if not value:
        return ""
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    return value


def update_profile(
    display_name: str,
    avatar_file=None,
    bio: str = "",
    suno_url: str = "",
    spotify_url: str = "",
    youtube_url: str = "",
    instagram_url: str = "",
    website_url: str = "",
) -> bool:
    sb = get_supabase_client()
    auth = get_auth_user()
    if not sb or not auth:
        return False
    display_name = clean_text(display_name, 80)
    bio = clean_text(bio, 500)
    if has_bad_words(display_name + bio):
        st.error("프로필 내용에 사용할 수 없는 표현이 포함되어 있습니다.")
        return False
    payload = {
        "display_name": display_name or auth.get("name") or auth.get("email") or "Busy User",
        "bio": bio,
        "suno_url": normalize_url(suno_url),
        "spotify_url": normalize_url(spotify_url),
        "youtube_url": normalize_url(youtube_url),
        "instagram_url": normalize_url(instagram_url),
        "website_url": normalize_url(website_url),
        "updated_at": now_iso(),
    }
    if avatar_file:
        ok, msg, ext = validate_upload_file(avatar_file, AVATAR_EXTS, MAX_AVATAR_MB, "아바타")
        if not ok:
            st.error(msg)
            return False
        path, url, err = upload_to_bucket(AVATAR_BUCKET, avatar_file, auth["user_id"], ext)
        if err:
            st.error(f"아바타 업로드 실패: {err}")
            return False
        payload.update({"avatar_path": path, "avatar_url": url})
    try:
        sb.table("bc_profiles").upsert({"user_id": auth["user_id"], "email": auth.get("email"), **payload}, on_conflict="user_id").execute()
        return True
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return False


def list_songs(limit: int = 300, only_public: bool = True, order: str = "score") -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    if not sb:
        return []
    try:
        q = sb.table("bc_songs").select("*, bc_profiles(display_name, avatar_url)")
        if only_public:
            q = q.eq("visibility", "public").eq("status", "active")
        if order == "new":
            q = q.order("created_at", desc=True)
        elif order == "liked":
            q = q.order("like_count", desc=True).order("created_at", desc=True)
        elif order == "played":
            q = q.order("play_count", desc=True).order("created_at", desc=True)
        else:
            q = q.order("trend_score", desc=True).order("created_at", desc=True)
        return q.limit(limit).execute().data or []
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return []


def get_song(song_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    if not sb:
        return None
    try:
        res = sb.table("bc_songs").select("*, bc_profiles(display_name, avatar_url)").eq("id", song_id).limit(1).execute()
        return (res.data or [None])[0]
    except Exception:
        return None


def list_my_songs() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    uid = get_user_id()
    if not sb or not uid:
        return []
    try:
        return sb.table("bc_songs").select("*").eq("uploader_user_id", uid).order("created_at", desc=True).execute().data or []
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return []


def calculate_trend_score(play_count: int, like_count: int, comment_count: int, created_at: str) -> float:
    import math
    freshness = 0.0
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        age_hours = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 3600)
        freshness = max(0.0, 1.0 - age_hours / (7 * 24)) ** 1.25 * 30.0
    except Exception:
        freshness = 0.0
    return round(math.log1p(play_count or 0) * 1.0 + math.log1p(like_count or 0) * 3.0 + math.log1p(comment_count or 0) * 4.0 + freshness, 6)


def refresh_song_counts(song_id: str) -> None:
    sb = get_supabase_client()
    if not sb or not song_id:
        return
    try:
        likes = sb.table("bc_song_likes").select("song_id", count="exact").eq("song_id", song_id).execute().count or 0
        plays = sb.table("bc_play_events").select("song_id", count="exact").eq("song_id", song_id).execute().count or 0
        comments = sb.table("bc_comments").select("song_id", count="exact").eq("song_id", song_id).eq("status", "visible").execute().count or 0
        song = get_song(song_id) or {}
        score = calculate_trend_score(plays, likes, comments, song.get("created_at") or now_iso())
        sb.table("bc_songs").update({
            "like_count": likes,
            "play_count": plays,
            "comment_count": comments,
            "trend_score": score,
            "updated_at": now_iso(),
        }).eq("id", song_id).execute()
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)


def create_song(title: str, style_tags: str, lyrics: str, audio_file, cover_file, comments_enabled: bool, description: str = "") -> Optional[str]:
    sb = get_supabase_client()
    auth = get_auth_user()
    if not sb or not auth:
        st.error("로그인이 필요합니다.")
        return None
    title = clean_text(title, 160)
    style_tags = clean_text(style_tags, 300)
    lyrics = clean_text(lyrics, 20000)
    description = clean_text(description, 2000)
    if not title:
        st.error("노래 제목을 입력하세요.")
        return None
    if has_bad_words(title) or has_bad_words(style_tags) or has_bad_words(description):
        st.error("제목/태그/설명에 사용할 수 없는 표현이 포함되어 있습니다.")
        return None
    ok, msg, audio_ext = validate_upload_file(audio_file, AUDIO_EXTS, MAX_AUDIO_MB, "음원")
    if not ok:
        st.error(msg)
        return None
    ok, msg, cover_ext = validate_upload_file(cover_file, COVER_EXTS, MAX_COVER_MB, "앨범 이미지")
    if not ok:
        st.error(msg)
        return None
    song_id = str(uuid.uuid4())
    audio_path, audio_url, audio_err = upload_to_bucket(AUDIO_BUCKET, audio_file, song_id, audio_ext)
    if audio_err:
        st.error(f"음원 업로드 실패: {audio_err}")
        return None
    cover_path, cover_url, cover_err = upload_to_bucket(COVER_BUCKET, cover_file, song_id, cover_ext)
    if cover_err:
        delete_storage_path(AUDIO_BUCKET, audio_path or "")
        st.error(f"앨범 이미지 업로드 실패: {cover_err}")
        return None
    now = now_iso()
    row = {
        "id": song_id,
        "uploader_user_id": auth["user_id"],
        "title": title,
        "artist_name": ensure_profile().get("display_name") if ensure_profile() else auth.get("name"),
        "description": description,
        "style_tags": style_tags,
        "lyrics": lyrics,
        "audio_path": audio_path,
        "audio_url": audio_url,
        "cover_path": cover_path,
        "cover_url": cover_url,
        "comments_enabled": bool(comments_enabled),
        "visibility": "public",
        "status": "active",
        "rights_confirmed": True,
        "rights_confirmed_at": now,
        "created_at": now,
        "updated_at": now,
        "trend_score": calculate_trend_score(0, 0, 0, now),
    }
    try:
        sb.table("bc_songs").insert(row).execute()
        return song_id
    except Exception as exc:
        delete_storage_path(AUDIO_BUCKET, audio_path or "")
        delete_storage_path(COVER_BUCKET, cover_path or "")
        st.error(f"곡 등록 실패: {exc}")
        return None


def update_song(song_id: str, fields: Dict[str, Any], new_cover_file=None, new_audio_file=None) -> bool:
    sb = get_supabase_client()
    uid = get_user_id()
    if not sb or not uid:
        return False
    song = get_song(song_id)
    if not song or song.get("uploader_user_id") != uid:
        st.error("수정 권한이 없습니다.")
        return False
    payload = {k: v for k, v in fields.items() if k in {"title", "description", "style_tags", "lyrics", "comments_enabled", "visibility", "status"}}
    for key in ["title", "description", "style_tags", "lyrics"]:
        if key in payload:
            payload[key] = clean_text(payload[key], 20000 if key == "lyrics" else 2000)
    if any(has_bad_words(str(payload.get(k, ""))) for k in ["title", "description", "style_tags"]):
        st.error("사용할 수 없는 표현이 포함되어 있습니다.")
        return False
    if new_cover_file:
        ok, msg, ext = validate_upload_file(new_cover_file, COVER_EXTS, MAX_COVER_MB, "앨범 이미지")
        if not ok:
            st.error(msg)
            return False
        path, url, err = upload_to_bucket(COVER_BUCKET, new_cover_file, song_id, ext)
        if err:
            st.error(f"앨범 이미지 업로드 실패: {err}")
            return False
        delete_storage_path(COVER_BUCKET, song.get("cover_path") or "")
        payload.update({"cover_path": path, "cover_url": url})
    if new_audio_file:
        ok, msg, ext = validate_upload_file(new_audio_file, AUDIO_EXTS, MAX_AUDIO_MB, "음원")
        if not ok:
            st.error(msg)
            return False
        path, url, err = upload_to_bucket(AUDIO_BUCKET, new_audio_file, song_id, ext)
        if err:
            st.error(f"음원 업로드 실패: {err}")
            return False
        delete_storage_path(AUDIO_BUCKET, song.get("audio_path") or "")
        payload.update({"audio_path": path, "audio_url": url})
    payload["updated_at"] = now_iso()
    try:
        sb.table("bc_songs").update(payload).eq("id", song_id).eq("uploader_user_id", uid).execute()
        refresh_song_counts(song_id)
        return True
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return False


def delete_song(song_id: str) -> bool:
    sb = get_supabase_client()
    uid = get_user_id()
    if not sb or not uid:
        return False
    song = get_song(song_id)
    if not song or song.get("uploader_user_id") != uid:
        st.error("삭제 권한이 없습니다.")
        return False
    try:
        sb.table("bc_songs").update({"status": "deleted", "visibility": "private", "updated_at": now_iso()}).eq("id", song_id).eq("uploader_user_id", uid).execute()
        return True
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return False


def toggle_song_like(song_id: str) -> Optional[bool]:
    sb = get_supabase_client()
    if not sb or not song_id:
        return None
    key = actor_key()
    try:
        existing = sb.table("bc_song_likes").select("id").eq("song_id", song_id).eq("actor_key", key).limit(1).execute().data or []
        if existing:
            sb.table("bc_song_likes").delete().eq("id", existing[0]["id"]).execute()
            liked = False
        else:
            sb.table("bc_song_likes").insert({"song_id": song_id, "actor_key": key, "user_id": get_user_id(), "session_id": get_session_id()}).execute()
            liked = True
        refresh_song_counts(song_id)
        return liked
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return None


def liked_song_ids(song_ids: List[str]) -> set[str]:
    sb = get_supabase_client()
    if not sb or not song_ids:
        return set()
    try:
        rows = sb.table("bc_song_likes").select("song_id").eq("actor_key", actor_key()).in_("song_id", song_ids).execute().data or []
        return {str(r["song_id"]) for r in rows}
    except Exception:
        return set()


def add_comment(song_id: str, body: str) -> bool:
    sb = get_supabase_client()
    uid = get_user_id()
    if not sb or not uid:
        st.error("댓글은 로그인한 사용자만 작성할 수 있습니다.")
        return False
    song = get_song(song_id)
    if not song or not song.get("comments_enabled", True):
        st.error("이 곡은 댓글 작성이 비활성화되어 있습니다.")
        return False
    body = clean_text(body, 500)
    if len(body) < 2:
        st.error("댓글은 2자 이상 입력하세요.")
        return False
    if len(body) > 500:
        st.error("댓글은 500자 이하로 입력하세요.")
        return False
    if has_bad_words(body):
        st.error("댓글에 사용할 수 없는 표현이 포함되어 있습니다.")
        return False
    try:
        prof = ensure_profile() or {}
        sb.table("bc_comments").insert({
            "song_id": song_id,
            "user_id": uid,
            "display_name": prof.get("display_name") or "Busy User",
            "body": body,
            "status": "visible",
        }).execute()
        refresh_song_counts(song_id)
        return True
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return False


def list_comments(song_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    if not sb:
        return []
    try:
        return sb.table("bc_comments").select("*").eq("song_id", song_id).eq("status", "visible").order("created_at", desc=True).limit(limit).execute().data or []
    except Exception:
        return []


def toggle_comment_like(comment_id: str) -> Optional[bool]:
    sb = get_supabase_client()
    if not sb or not comment_id:
        return None
    key = actor_key()
    try:
        existing = sb.table("bc_comment_likes").select("id").eq("comment_id", comment_id).eq("actor_key", key).limit(1).execute().data or []
        if existing:
            sb.table("bc_comment_likes").delete().eq("id", existing[0]["id"]).execute()
            liked = False
        else:
            sb.table("bc_comment_likes").insert({"comment_id": comment_id, "actor_key": key, "user_id": get_user_id(), "session_id": get_session_id()}).execute()
            liked = True
        # refresh aggregate
        cnt = sb.table("bc_comment_likes").select("comment_id", count="exact").eq("comment_id", comment_id).execute().count or 0
        sb.table("bc_comments").update({"like_count": cnt}).eq("id", comment_id).execute()
        return liked
    except Exception as exc:
        st.session_state["busy_last_error"] = str(exc)
        return None
