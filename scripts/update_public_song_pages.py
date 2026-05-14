import os
import json
import time
import random
import math
import requests
import pandas as pd
from datetime import datetime, timezone

from ranking_core import (
    add_growth_features as core_add_growth_features,
    prepare_history,
    restore_created_at_from_history as core_restore_created_at_from_history,
    score_songs as core_score_songs,
    serialize_datetime_columns_for_csv,
)

from text_utils import (
    clean_list_or_text as normalize_list_or_text,
    clean_text,
    is_blank_value as text_is_blank_value,
    mojibake_report,
    normalize_record_text,
    normalize_text_columns,
)

DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"
ARCHIVE_PATH = "data/suno_song_archive.csv"
RANK_HISTORY_PATH = "data/suno_rank_history.csv"

REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "1.2"))
MAX_UPDATE_ROWS = int(os.getenv("MAX_UPDATE_ROWS", "1000"))
FETCH_NEW_SONGS = os.getenv("FETCH_NEW_SONGS", "1").strip().lower() not in {"0", "false", "no", "off"}
KEEP_EXPIRED_SONGS_IN_DB = os.getenv("KEEP_EXPIRED_SONGS_IN_DB", "0").strip().lower() in {"1", "true", "yes", "on"}

# Supabase 누적 운영 최적화: 전체 곡은 보관하되 fetch 대상은 tier/next_check_at로 제한한다.
UPDATE_TIERING_ENABLED = os.getenv("UPDATE_TIERING_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
HOT_REFRESH_HOURS = float(os.getenv("HOT_REFRESH_HOURS", "0"))
PLAYLIST_REFRESH_HOURS = float(os.getenv("PLAYLIST_REFRESH_HOURS", "24"))
WARM_REFRESH_HOURS = float(os.getenv("WARM_REFRESH_HOURS", "6"))
COLD_REFRESH_HOURS = float(os.getenv("COLD_REFRESH_HOURS", "72"))
FROZEN_REFRESH_HOURS = float(os.getenv("FROZEN_REFRESH_HOURS", "168"))
FETCH_FAIL_FREEZE_THRESHOLD = int(os.getenv("FETCH_FAIL_FREEZE_THRESHOLD", "10"))
FETCH_FAIL_BACKOFF_THRESHOLD = int(os.getenv("FETCH_FAIL_BACKOFF_THRESHOLD", "3"))
RAIN_CREW_HANDLES = {h.strip().lower().lstrip("@") for h in os.getenv("RAIN_CREW_HANDLES", "busystudio,gaaia,stone3ah,joonoc,eve_rain,djjobs,katarina_blu,katarina_suno,jenapop,n_dal,shout4all,suzushie").split(",") if h.strip()}

# 무로그인 new_songs는 page_size 50까지 가능, 100은 서버가 거절함
NEW_SONGS_PAGES = int(os.getenv("NEW_SONGS_PAGES", "3"))
NEW_SONGS_PAGE_SIZE = int(os.getenv("NEW_SONGS_PAGE_SIZE", "50"))

# 단기 트렌딩용: Suno created_at 기준 N일 지난 곡은 active DB/history에서 제외하고 archive에 보존
SONG_RETENTION_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))
RETENTION_HOURS = SONG_RETENTION_DAYS * 24
GROWTH_WINDOW_HOURS = int(os.getenv("GROWTH_WINDOW_HOURS", "3"))
PLAY_WEIGHT = float(os.getenv("PLAY_WEIGHT", "1.0"))
LIKE_WEIGHT = float(os.getenv("LIKE_WEIGHT", "3.0"))
COMMENT_WEIGHT = float(os.getenv("COMMENT_WEIGHT", "4.0"))
GROWTH_WEIGHT = float(os.getenv("GROWTH_WEIGHT", "1.5"))
FRESHNESS_WEIGHT = float(os.getenv("FRESHNESS_WEIGHT", "35.0"))
FRESHNESS_POWER = float(os.getenv("FRESHNESS_POWER", "1.35"))

if NEW_SONGS_PAGE_SIZE > 50:
    NEW_SONGS_PAGE_SIZE = 50

UNIFIED_FEED_URL = "https://studio-api-prod.suno.com/api/unified/feed"

PUBLIC_HEADERS_JSON = {
    "accept": "*/*",
    "accept-language": "ko,en-US;q=0.9,en;q=0.8",
    "content-type": "application/json",
    "origin": "https://suno.com",
    "referer": "https://suno.com/explore",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}

PUBLIC_HEADERS_RSC = {
    "accept": "*/*",
    "accept-language": "ko,en-US;q=0.9,en;q=0.8",
    "referer": "https://suno.com/explore",
    "rsc": "1",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_data_files():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(DB_PATH):
        pd.DataFrame(columns=[
            "id", "title", "handle", "display_name", "user_id",
            "created_at", "first_seen_at", "last_checked_at",
            "play_count", "upvote_count", "comment_count", "flag_count",
            "is_contest_clip", "contest_ids", "download_disabled_reason",
            "is_public", "is_hidden", "is_trashed", "explicit",
            "model", "major_model_version", "display_tags", "duration",
            "lyrics", "prompt", "gpt_description_prompt",
            "song_url", "audio_url", "image_url", "source",
            "integrated_lufs", "true_peak_db", "loudness_gain_db",
            "loudness_target_lufs", "loudness_true_peak_ceiling_db",
            "loudness_checked_at", "loudness_status", "loudness_error",
            "loudness_audio_url_hash", "loudness_input_lra",
            "loudness_input_thresh", "loudness_target_offset",
        ]).to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    if not os.path.exists(HISTORY_PATH):
        pd.DataFrame(columns=[
            "checked_at", "id", "title", "handle", "created_at",
            "play_count", "upvote_count", "comment_count", "flag_count",
        ]).to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

    if not os.path.exists(ARCHIVE_PATH):
        pd.DataFrame(columns=get_archive_columns()).to_csv(
            ARCHIVE_PATH,
            index=False,
            encoding="utf-8-sig",
        )

    if not os.path.exists(RANK_HISTORY_PATH):
        pd.DataFrame(columns=get_rank_history_columns()).to_csv(
            RANK_HISTORY_PATH,
            index=False,
            encoding="utf-8-sig",
        )


def get_rank_history_columns():
    return [
        "captured_at", "id", "rank",
        "trend_score", "base_score", "growth_score", "freshness_score",
        "play_count", "upvote_count", "comment_count", "adjusted_comment_count",
    ]


def get_archive_columns():
    return [
        "archived_at", "archive_reason",
        "id", "title", "handle", "display_name", "user_id",
        "created_at", "first_seen_at", "last_checked_at",
        "play_count", "upvote_count", "comment_count", "adjusted_comment_count",
        "comment_quality_ratio", "meaningful_count", "generic_count",
        "mention_only_count", "emoji_only_count", "flag_count",
        "final_rank", "best_rank", "best_rank_at",
        "first_charted_at", "last_charted_at",
        "top10_count", "top50_count", "top200_count", "chart_in_count",
        "final_trend_score", "final_base_score", "final_growth_score", "final_freshness_score",
        "best_trend_score", "best_score_at",
        "peak_play_count", "peak_upvote_count", "peak_comment_count", "peak_adjusted_comment_count",
        "model", "major_model_version", "display_tags", "duration",
        "lyrics", "prompt", "gpt_description_prompt",
        "song_url", "audio_url", "image_url", "source",
        "integrated_lufs", "true_peak_db", "loudness_gain_db",
        "loudness_target_lufs", "loudness_true_peak_ceiling_db",
        "loudness_checked_at", "loudness_status", "loudness_error",
        "loudness_audio_url_hash", "loudness_input_lra",
        "loudness_input_thresh", "loudness_target_offset",
    ]


def is_blank_value(value):
    return text_is_blank_value(value)

def clean_text_field(value):
    if is_blank_value(value):
        return None
    if isinstance(value, (dict, list)):
        return None
    s = clean_text(value)
    return s or None

def first_non_empty(*values):
    for value in values:
        if is_blank_value(value):
            continue
        return value

    return None


def get_old_value(old_row, key, default=None):
    if old_row is None:
        return default

    try:
        value = old_row.get(key, default)
    except Exception:
        return default

    return first_non_empty(value, default)


def clean_list_or_text(value):
    s = normalize_list_or_text(value)
    return s or None

def get_nested_dict(obj, key):
    value = obj.get(key)

    if isinstance(value, dict):
        return value

    return {}


def is_contest(song):
    metadata = song.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    return (
        song.get("is_contest_clip") is True
        or song.get("is_contest_base_clip") is True
        or bool(metadata.get("contest_ids"))
        or song.get("download_disabled_reason") == "remix_contest"
    )


def flatten_song(song, old_row=None, source="public"):
    metadata = song.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    user = get_nested_dict(song, "user")
    clip = get_nested_dict(song, "clip")

    song_id = first_non_empty(
        song.get("id"),
        clip.get("id"),
        get_old_value(old_row, "id"),
    )

    old_source = first_non_empty(
        get_old_value(old_row, "source"),
        source,
    )

    created_at = first_non_empty(
        song.get("created_at"),
        song.get("createdAt"),
        song.get("created"),
        clip.get("created_at"),
        clip.get("createdAt"),
        metadata.get("created_at"),
        metadata.get("createdAt"),
        get_old_value(old_row, "created_at"),
    )

    title = first_non_empty(
        song.get("title"),
        clip.get("title"),
        metadata.get("title"),
        get_old_value(old_row, "title"),
        "Untitled",
    )

    handle = first_non_empty(
        song.get("handle"),
        user.get("handle"),
        metadata.get("handle"),
        get_old_value(old_row, "handle"),
    )

    display_name = first_non_empty(
        song.get("display_name"),
        song.get("displayName"),
        user.get("display_name"),
        user.get("displayName"),
        metadata.get("display_name"),
        metadata.get("displayName"),
        get_old_value(old_row, "display_name"),
    )

    user_id = first_non_empty(
        song.get("user_id"),
        song.get("userId"),
        user.get("id"),
        metadata.get("user_id"),
        get_old_value(old_row, "user_id"),
    )

    prompt = first_non_empty(
        clean_text_field(song.get("prompt")),
        clean_text_field(clip.get("prompt")),
        clean_text_field(metadata.get("prompt")),
        clean_text_field(song.get("lyric")),
        clean_text_field(metadata.get("lyric")),
        get_old_value(old_row, "prompt"),
    )

    lyrics = first_non_empty(
        clean_text_field(song.get("lyrics")),
        clean_text_field(clip.get("lyrics")),
        clean_text_field(metadata.get("lyrics")),
        clean_text_field(song.get("lyric")),
        clean_text_field(clip.get("lyric")),
        clean_text_field(metadata.get("lyric")),
        prompt,
        get_old_value(old_row, "lyrics"),
    )

    gpt_description_prompt = first_non_empty(
        clean_text_field(song.get("gpt_description_prompt")),
        clean_text_field(clip.get("gpt_description_prompt")),
        clean_text_field(metadata.get("gpt_description_prompt")),
        clean_text_field(song.get("gpt_description")),
        clean_text_field(clip.get("gpt_description")),
        clean_text_field(metadata.get("gpt_description")),
        clean_text_field(song.get("description")),
        clean_text_field(metadata.get("description")),
        get_old_value(old_row, "gpt_description_prompt"),
    )

    display_tags = first_non_empty(
        clean_list_or_text(song.get("display_tags")),
        clean_list_or_text(clip.get("display_tags")),
        clean_list_or_text(metadata.get("display_tags")),
        clean_list_or_text(metadata.get("tags")),
        clean_list_or_text(song.get("tags")),
        get_old_value(old_row, "display_tags"),
    )

    contest_ids = first_non_empty(
        clean_list_or_text(metadata.get("contest_ids")),
        clean_list_or_text(song.get("contest_ids")),
        get_old_value(old_row, "contest_ids"),
    )

    audio_url = first_non_empty(
        song.get("audio_url"),
        song.get("audioUrl"),
        song.get("audio_url_mp3"),
        song.get("stream_audio_url"),
        song.get("streamAudioUrl"),
        clip.get("audio_url"),
        clip.get("audioUrl"),
        metadata.get("audio_url"),
        metadata.get("audioUrl"),
        get_old_value(old_row, "audio_url"),
    )

    image_url = first_non_empty(
        song.get("image_url"),
        song.get("imageUrl"),
        song.get("image_large_url"),
        song.get("imageLargeUrl"),
        clip.get("image_url"),
        clip.get("imageUrl"),
        metadata.get("image_url"),
        metadata.get("imageUrl"),
        metadata.get("image_large_url"),
        get_old_value(old_row, "image_url"),
    )

    model = first_non_empty(
        song.get("model_name"),
        song.get("model"),
        metadata.get("model_name"),
        metadata.get("model"),
        song.get("major_model_version"),
        metadata.get("major_model_version"),
        get_old_value(old_row, "model"),
    )

    major_model_version = first_non_empty(
        song.get("major_model_version"),
        metadata.get("major_model_version"),
        get_old_value(old_row, "major_model_version"),
    )

    duration = first_non_empty(
        song.get("duration"),
        clip.get("duration"),
        metadata.get("duration"),
        get_old_value(old_row, "duration"),
    )

    now_txt = now_iso()

    row = {
        "id": song_id,
        "title": title,
        "handle": handle,
        "display_name": display_name,
        "user_id": user_id,

        "created_at": created_at,
        "first_seen_at": first_non_empty(
            get_old_value(old_row, "first_seen_at"),
            now_txt,
        ),
        "last_checked_at": now_txt,

        "play_count": first_non_empty(
            song.get("play_count"),
            song.get("playCount"),
            clip.get("play_count"),
            get_old_value(old_row, "play_count"),
            0,
        ),
        "upvote_count": first_non_empty(
            song.get("upvote_count"),
            song.get("upvoteCount"),
            song.get("like_count"),
            song.get("likeCount"),
            clip.get("upvote_count"),
            get_old_value(old_row, "upvote_count"),
            0,
        ),
        "comment_count": first_non_empty(
            song.get("comment_count"),
            song.get("commentCount"),
            clip.get("comment_count"),
            get_old_value(old_row, "comment_count"),
            0,
        ),
        "flag_count": first_non_empty(
            song.get("flag_count"),
            song.get("flagCount"),
            clip.get("flag_count"),
            get_old_value(old_row, "flag_count"),
            0,
        ),

        "is_contest_clip": first_non_empty(
            song.get("is_contest_clip"),
            get_old_value(old_row, "is_contest_clip"),
        ),
        "contest_ids": contest_ids,
        "download_disabled_reason": first_non_empty(
            song.get("download_disabled_reason"),
            get_old_value(old_row, "download_disabled_reason"),
        ),

        "is_public": first_non_empty(
            song.get("is_public"),
            get_old_value(old_row, "is_public"),
        ),
        "is_hidden": first_non_empty(
            song.get("is_hidden"),
            get_old_value(old_row, "is_hidden"),
        ),
        "is_trashed": first_non_empty(
            song.get("is_trashed"),
            get_old_value(old_row, "is_trashed"),
        ),
        "explicit": first_non_empty(
            song.get("explicit"),
            get_old_value(old_row, "explicit"),
        ),

        "model": model,
        "major_model_version": major_model_version,
        "display_tags": display_tags,
        "duration": duration,

        "lyrics": lyrics,
        "prompt": prompt,
        "gpt_description_prompt": gpt_description_prompt,

        "song_url": first_non_empty(
            song.get("song_url"),
            song.get("songUrl"),
            f"https://suno.com/song/{song_id}" if song_id else None,
            get_old_value(old_row, "song_url"),
        ),
        "audio_url": audio_url,
        "image_url": image_url,
        "source": old_source,

        # 랭킹 변동 계산용 기존 값 보존
        "previous_rank": get_old_value(old_row, "previous_rank"),
        "current_rank": get_old_value(old_row, "current_rank"),
        "rank_change": get_old_value(old_row, "rank_change"),
        "rank_status": get_old_value(old_row, "rank_status"),

        # 댓글 품질 분석 값 보존
        "adjusted_comment_count": get_old_value(old_row, "adjusted_comment_count"),
        "effective_comment_count": get_old_value(old_row, "effective_comment_count"),
        "comment_quality_ratio": get_old_value(old_row, "comment_quality_ratio"),
        "analyzed_comment_count": get_old_value(old_row, "analyzed_comment_count"),
        "meaningful_count": get_old_value(old_row, "meaningful_count"),
        "generic_count": get_old_value(old_row, "generic_count"),
        "mention_only_count": get_old_value(old_row, "mention_only_count"),
        "emoji_only_count": get_old_value(old_row, "emoji_only_count"),
        "comment_quality_summary": get_old_value(old_row, "comment_quality_summary"),
        "comment_quality_checked_at": get_old_value(old_row, "comment_quality_checked_at"),

        # Supabase 누적 운영 메타데이터
        "status": "active",
        "update_tier": get_old_value(old_row, "update_tier"),
        "next_check_at": get_old_value(old_row, "next_check_at"),
        "fetch_fail_count": 0,
        "last_fetch_error": "",
        "last_change_at": get_old_value(old_row, "last_change_at"),
        "playlist_ref_count": get_old_value(old_row, "playlist_ref_count"),
        "comments_fetch_needed": get_old_value(old_row, "comments_fetch_needed"),
        "last_comment_fetch_at": get_old_value(old_row, "last_comment_fetch_at"),
    }

    # 변화 감지: 수치가 바뀌었으면 last_change_at 갱신, 댓글 수 증가 시 댓글 수집 후보 표시
    try:
        old_play = float(get_old_value(old_row, "play_count", 0) or 0)
        old_like = float(get_old_value(old_row, "upvote_count", 0) or 0)
        old_comment = float(get_old_value(old_row, "comment_count", 0) or 0)
        new_play = float(row.get("play_count") or 0)
        new_like = float(row.get("upvote_count") or 0)
        new_comment = float(row.get("comment_count") or 0)
        if new_play != old_play or new_like != old_like or new_comment != old_comment:
            row["last_change_at"] = now_txt
        if new_comment > old_comment:
            row["comments_fetch_needed"] = "1"
    except Exception:
        pass

    return normalize_record_text(row)

def history_snapshot(row):
    return {
        "checked_at": now_iso(),
        "id": row.get("id"),
        "title": row.get("title"),
        "handle": row.get("handle"),
        "created_at": row.get("created_at"),
        "play_count": row.get("play_count"),
        "upvote_count": row.get("upvote_count"),
        "comment_count": row.get("comment_count"),
        "flag_count": row.get("flag_count"),
    }


def extract_song_from_feed_item(item):
    if not isinstance(item, dict):
        return None

    if item.get("content_type") != "clip":
        return None

    song = item.get("content_item") or {}

    if not isinstance(song, dict):
        return None

    if not song.get("id"):
        return None

    return song


def fetch_public_new_songs():
    found = []
    logs = []

    cursor = None

    for page_idx in range(NEW_SONGS_PAGES):
        payload = {
            "feed_id": "new_songs",
            "cursor": cursor,
            "page_size": NEW_SONGS_PAGE_SIZE,
        }

        try:
            r = requests.post(
                UNIFIED_FEED_URL,
                headers=PUBLIC_HEADERS_JSON,
                json=payload,
                timeout=30,
            )

            if r.status_code == 404 and "returned no content" in r.text:
                logs.append(f"[new_songs] page={page_idx + 1}, cursor={cursor}, no content")
                break

            if r.status_code != 200:
                logs.append(
                    f"[new_songs] page={page_idx + 1}, cursor={cursor}, "
                    f"HTTP {r.status_code}: {r.text[:300]}"
                )
                break

            data = r.json()
            feed = data.get("feed") or {}
            items = feed.get("items") or []
            next_cursor = feed.get("next_cursor")

            page_songs = []
            contest_count = 0

            for item in items:
                song = extract_song_from_feed_item(item)
                if song is None:
                    continue

                if is_contest(song):
                    contest_count += 1

                page_songs.append(song)

            found.extend(page_songs)

            logs.append(
                f"[new_songs] page={page_idx + 1}, cursor={cursor}, "
                f"page_size={NEW_SONGS_PAGE_SIZE}, raw_items={len(items)}, "
                f"songs={len(page_songs)}, contest_included={contest_count}, "
                f"next_cursor={next_cursor}"
            )

            if not items:
                break

            if next_cursor is not None:
                cursor = str(next_cursor)
            else:
                break

        except Exception as e:
            logs.append(f"[new_songs] page={page_idx + 1}, cursor={cursor}, ERROR={repr(e)}")
            break

        time.sleep(0.5)

    return found, logs


def extract_balanced_json_object(text, start_index):
    if start_index < 0 or start_index >= len(text) or text[start_index] != "{":
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start_index, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

            if depth == 0:
                return text[start_index:i + 1]

    return None


def extract_clip_from_rsc_text(text):
    key = '"clip":'
    pos = text.find(key)

    if pos == -1:
        return None

    brace_start = text.find("{", pos + len(key))

    if brace_start == -1:
        return None

    obj_text = extract_balanced_json_object(text, brace_start)

    if not obj_text:
        return None

    try:
        return json.loads(obj_text)
    except Exception:
        return None


def fetch_song_public(song_id):
    rsc_key = f"rsc{random.randint(100000, 999999)}"
    url = f"https://suno.com/song/{song_id}?_rsc={rsc_key}"

    try:
        r = requests.get(url, headers=PUBLIC_HEADERS_RSC, timeout=30)

        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"

        clip = extract_clip_from_rsc_text(r.text)

        if not clip:
            return None, "clip_not_found"

        return clip, ""

    except Exception as e:
        return None, repr(e)


def add_new_songs_to_db(db, songs):
    if db.empty or "id" not in db.columns:
        existing_ids = set()
    else:
        existing_ids = set(db["id"].dropna().astype(str))

    new_rows = []
    duplicate_count = 0

    for song in songs:
        song_id = str(song.get("id"))

        if not song_id or song_id == "None" or song_id == "nan":
            continue

        if song_id in existing_ids:
            duplicate_count += 1
            continue

        row = flatten_song(song, old_row=None, source="new_songs_public")
        new_rows.append(row)
        existing_ids.add(song_id)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        db = pd.concat([db, new_df], ignore_index=True)

    return db, len(new_rows), duplicate_count



def utc_timestamp():
    return pd.Timestamp.now(tz="UTC")


def normalize_handle_for_tier(value):
    return str(value or "").strip().lower().lstrip("@")


def get_playlist_referenced_ids():
    """Return song IDs referenced by Cloud Playlists.

    This uses Supabase directly when available. If Supabase is unavailable, it
    safely returns an empty set so the update pipeline can still run.
    """
    try:
        from supabase_raw_io import get_client, _fetch_all
        sb = get_client()
        rows = _fetch_all(sb, "playlist_items")
        return {str(row.get("song_id")) for row in rows if row.get("song_id")}
    except Exception as exc:
        print(f"[playlist_refs] skipped: {exc}")
        return set()


def compute_update_tier(row, now=None, playlist_ids=None):
    now = now or utc_timestamp()
    playlist_ids = playlist_ids or set()
    song_id = str(row.get("id") or "")
    status = str(row.get("status") or "").strip().lower()
    fail_count = pd.to_numeric(pd.Series([row.get("fetch_fail_count")]), errors="coerce").fillna(0).iloc[0]

    if status in {"frozen", "deleted", "unavailable", "private"} or int(fail_count) >= FETCH_FAIL_FREEZE_THRESHOLD:
        return "frozen"

    created_at = pd.to_datetime(row.get("created_at"), errors="coerce", utc=True)
    if pd.isna(created_at):
        return "hot"

    if created_at >= now - pd.Timedelta(days=SONG_RETENTION_DAYS):
        return "hot"

    if song_id in playlist_ids:
        return "playlist"

    handle = normalize_handle_for_tier(row.get("handle"))
    if handle in RAIN_CREW_HANDLES:
        return "warm"

    return "cold"


def tier_refresh_hours(tier):
    return {
        "hot": HOT_REFRESH_HOURS,
        "playlist": PLAYLIST_REFRESH_HOURS,
        "warm": WARM_REFRESH_HOURS,
        "cold": COLD_REFRESH_HOURS,
        "frozen": FROZEN_REFRESH_HOURS,
    }.get(str(tier or "cold"), COLD_REFRESH_HOURS)


def is_due_for_tier(row, tier, now=None):
    now = now or utc_timestamp()
    if not UPDATE_TIERING_ENABLED:
        return True

    next_check = pd.to_datetime(row.get("next_check_at"), errors="coerce", utc=True)
    if pd.notna(next_check):
        return next_check <= now

    last_checked = pd.to_datetime(row.get("last_checked_at"), errors="coerce", utc=True)
    hours = tier_refresh_hours(tier)
    if pd.isna(last_checked):
        # Missing last_checked active/hot rows should be refreshed quickly. Old cold rows can wait.
        return tier in {"hot", "playlist", "warm"}
    return last_checked <= now - pd.Timedelta(hours=hours)


def choose_rows_to_update(db):
    """Pick rows for detail refresh using tiering + next_check_at.

    Storage remains append/keep-all in suno_songs. Fetching is limited by:
    - hot: 4-day ranking candidates or missing created_at
    - playlist: old songs referenced by user playlists
    - warm: Rain Crew/important handles
    - cold: old unreferenced songs, low frequency
    - frozen: repeated failures/deleted/private, very low frequency
    """
    if db.empty:
        return db

    out = db.copy()
    now = utc_timestamp()
    playlist_ids = get_playlist_referenced_ids() if UPDATE_TIERING_ENABLED else set()

    if "created_at" in out.columns:
        out["created_at_dt"] = pd.to_datetime(out["created_at"], errors="coerce", utc=True)
    else:
        out["created_at_dt"] = pd.NaT

    if "last_checked_at" in out.columns:
        out["last_checked_at_dt"] = pd.to_datetime(out["last_checked_at"], errors="coerce", utc=True)
    else:
        out["last_checked_at_dt"] = pd.NaT

    if "next_check_at" in out.columns:
        out["next_check_at_dt"] = pd.to_datetime(out["next_check_at"], errors="coerce", utc=True)
    else:
        out["next_check_at_dt"] = pd.NaT

    out["computed_update_tier"] = out.apply(lambda r: compute_update_tier(r, now=now, playlist_ids=playlist_ids), axis=1)
    out["is_due"] = out.apply(lambda r: is_due_for_tier(r, r.get("computed_update_tier"), now=now), axis=1)

    tier_priority = {"hot": 0, "playlist": 1, "warm": 2, "cold": 3, "frozen": 4}
    out["tier_priority"] = out["computed_update_tier"].map(tier_priority).fillna(9).astype(int)
    out["missing_created_priority"] = out["created_at_dt"].isna().astype(int)
    out["missing_checked_priority"] = out["last_checked_at_dt"].isna().astype(int)

    due = out[out["is_due"]].copy()

    due = due.sort_values(
        by=["tier_priority", "missing_created_priority", "missing_checked_priority", "last_checked_at_dt", "created_at_dt"],
        ascending=[True, False, False, True, False],
        na_position="first",
    )

    print(
        f"[choose_update] tiering={int(UPDATE_TIERING_ENABLED)} max={MAX_UPDATE_ROWS}, "
        f"db_rows={len(out)}, due_rows={len(due)}, playlist_refs={len(playlist_ids)}, "
        f"tiers={out['computed_update_tier'].value_counts(dropna=False).to_dict()}"
    )

    selected = due.head(MAX_UPDATE_ROWS).copy()
    return selected.drop(
        columns=[
            "created_at_dt", "last_checked_at_dt", "next_check_at_dt",
            "missing_created_priority", "missing_checked_priority",
            "tier_priority", "is_due",
        ],
        errors="ignore",
    ).copy()


def restore_created_at_from_history(db):
    """Fill missing active DB created_at from history snapshots using the shared ranking core."""
    if db is None or db.empty:
        return db

    if not os.path.exists(HISTORY_PATH):
        print("[restore_created_at] skipped: history file missing")
        return db

    try:
        hist = pd.read_csv(HISTORY_PATH)
    except Exception as e:
        print(f"[restore_created_at] skipped: failed to read history: {e}")
        return db

    if hist.empty:
        print("[restore_created_at] skipped: empty history")
        return db

    before_valid = int(pd.to_datetime(db.get("created_at"), errors="coerce", utc=True).notna().sum()) if "created_at" in db.columns else 0
    restored_db = core_restore_created_at_from_history(db, prepare_history(hist))
    after_valid = int(pd.to_datetime(restored_db.get("created_at"), errors="coerce", utc=True).notna().sum()) if "created_at" in restored_db.columns else 0

    print(
        f"[restore_created_at] valid_before={before_valid}/{len(restored_db)}, "
        f"restored={after_valid - before_valid}, valid_after={after_valid}/{len(restored_db)}"
    )

    return restored_db

def to_number(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def load_history_for_archive():
    if not os.path.exists(HISTORY_PATH):
        return pd.DataFrame()

    hist = pd.read_csv(HISTORY_PATH)
    if hist.empty:
        return hist

    if "id" in hist.columns:
        hist["id"] = hist["id"].astype(str)
    if "checked_at" in hist.columns:
        hist["checked_at"] = pd.to_datetime(hist["checked_at"], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count"]:
        if col in hist.columns:
            hist[col] = to_number(hist[col])

    return hist


def add_growth_features_for_archive(db, hist, window_hours):
    """Compatibility wrapper; archive scoring uses ranking_core."""
    return core_add_growth_features(db, hist, window_hours)

def score_songs_for_archive(db, hist):
    """Score archive candidates with the same shared ranking core used by payload/rank movement."""
    hist_prepared = prepare_history(hist) if hist is not None and not hist.empty else pd.DataFrame()
    ranked = core_score_songs(db, hist_prepared).sort_values(
        "trend_score",
        ascending=False,
        na_position="last",
    ).copy()
    ranked["computed_rank"] = range(1, len(ranked) + 1)
    return ranked


def load_rank_history_for_archive():
    if not os.path.exists(RANK_HISTORY_PATH):
        return pd.DataFrame(columns=get_rank_history_columns())

    try:
        rank_hist = pd.read_csv(RANK_HISTORY_PATH)
    except Exception as e:
        print(f"[rank_history] failed to read for archive: {e}")
        return pd.DataFrame(columns=get_rank_history_columns())

    if rank_hist.empty:
        return rank_hist

    if "id" in rank_hist.columns:
        rank_hist["id"] = rank_hist["id"].astype(str)
    if "captured_at" in rank_hist.columns:
        rank_hist["captured_at_dt"] = pd.to_datetime(rank_hist["captured_at"], errors="coerce", utc=True)

    for col in [
        "rank", "trend_score", "base_score", "growth_score", "freshness_score",
        "play_count", "upvote_count", "comment_count", "adjusted_comment_count",
    ]:
        if col in rank_hist.columns:
            rank_hist[col] = pd.to_numeric(rank_hist[col], errors="coerce")

    return rank_hist


def summarize_rank_history(rank_hist, song_ids):
    cols = [
        "id", "best_rank_history", "best_rank_at", "best_trend_score_history", "best_score_at_history",
        "first_charted_at", "last_charted_at", "top10_count", "top50_count", "top200_count", "chart_in_count",
    ]
    if rank_hist is None or rank_hist.empty or "id" not in rank_hist.columns:
        return pd.DataFrame(columns=cols)

    wanted = set(str(x) for x in song_ids if not is_blank_value(x))
    if not wanted:
        return pd.DataFrame(columns=cols)

    rh = rank_hist[rank_hist["id"].astype(str).isin(wanted)].copy()
    if rh.empty:
        return pd.DataFrame(columns=cols)

    if "captured_at_dt" not in rh.columns:
        rh["captured_at_dt"] = pd.to_datetime(rh.get("captured_at"), errors="coerce", utc=True)

    rows = []
    for song_id, g in rh.groupby("id", dropna=False):
        g = g.copy()
        rank = pd.to_numeric(g.get("rank"), errors="coerce")
        score = pd.to_numeric(g.get("trend_score"), errors="coerce")
        captured = g.get("captured_at_dt")

        best_rank = rank.min(skipna=True)
        best_rank_at = pd.NA
        if rank.notna().any():
            best_rank_idx = rank.idxmin()
            best_rank_at = g.loc[best_rank_idx, "captured_at"] if "captured_at" in g.columns else pd.NA

        best_score = score.max(skipna=True)
        best_score_at = pd.NA
        if score.notna().any():
            best_score_idx = score.idxmax()
            best_score_at = g.loc[best_score_idx, "captured_at"] if "captured_at" in g.columns else pd.NA

        first_charted_at = pd.NA
        last_charted_at = pd.NA
        if captured is not None and captured.notna().any():
            first_idx = captured.idxmin()
            last_idx = captured.idxmax()
            first_charted_at = g.loc[first_idx, "captured_at"] if "captured_at" in g.columns else pd.NA
            last_charted_at = g.loc[last_idx, "captured_at"] if "captured_at" in g.columns else pd.NA

        rows.append({
            "id": str(song_id),
            "best_rank_history": best_rank,
            "best_rank_at": best_rank_at,
            "best_trend_score_history": best_score,
            "best_score_at_history": best_score_at,
            "first_charted_at": first_charted_at,
            "last_charted_at": last_charted_at,
            "top10_count": int((rank <= 10).sum()),
            "top50_count": int((rank <= 50).sum()),
            "top200_count": int((rank <= 200).sum()),
            "chart_in_count": int(rank.notna().sum()),
        })

    return pd.DataFrame(rows, columns=cols)


def prune_rank_history_by_active_ids(kept_ids):
    if not os.path.exists(RANK_HISTORY_PATH):
        return

    try:
        rank_hist = pd.read_csv(RANK_HISTORY_PATH)
    except Exception as e:
        print(f"[rank_history_prune] failed to read: {e}")
        return

    if rank_hist.empty or "id" not in rank_hist.columns:
        rank_hist.to_csv(RANK_HISTORY_PATH, index=False, encoding="utf-8-sig")
        return

    before = len(rank_hist)
    rank_hist["id"] = rank_hist["id"].astype(str)
    kept = rank_hist[rank_hist["id"].isin(set(str(x) for x in kept_ids))].copy()
    kept = serialize_datetime_columns_for_csv(kept)
    kept.to_csv(RANK_HISTORY_PATH, index=False, encoding="utf-8-sig")
    print(f"[rank_history_prune] before={before}, after={len(kept)}, removed={before - len(kept)}")


def archive_expired_songs(expired_db, scored_db):
    if expired_db.empty:
        return

    archive_now = now_iso()
    expired = expired_db.copy()
    expired["id"] = expired["id"].astype(str)

    rank_hist = load_rank_history_for_archive()
    rank_summary = summarize_rank_history(rank_hist, expired["id"].dropna().astype(str).tolist())
    if not rank_summary.empty:
        expired = expired.merge(rank_summary, on="id", how="left")

    scored_cols = [
        "id", "computed_rank", "trend_score", "base_score", "growth_score", "freshness_score",
    ]
    scored_lookup = scored_db[[c for c in scored_cols if c in scored_db.columns]].copy()
    if "id" in scored_lookup.columns:
        scored_lookup["id"] = scored_lookup["id"].astype(str)
        expired = expired.merge(scored_lookup, on="id", how="left")

    archive = expired.copy()
    archive["archived_at"] = archive_now
    archive["archive_reason"] = f"older_than_{SONG_RETENTION_DAYS}d"

    archive["final_rank"] = pd.to_numeric(archive.get("computed_rank"), errors="coerce")
    if "current_rank" in archive.columns:
        archive["final_rank"] = archive["final_rank"].fillna(pd.to_numeric(archive["current_rank"], errors="coerce"))

    archive["final_trend_score"] = pd.to_numeric(archive.get("trend_score"), errors="coerce")
    archive["final_base_score"] = pd.to_numeric(archive.get("base_score"), errors="coerce")
    archive["final_growth_score"] = pd.to_numeric(archive.get("growth_score"), errors="coerce")
    archive["final_freshness_score"] = pd.to_numeric(archive.get("freshness_score"), errors="coerce")

    if "best_rank" in archive.columns:
        archive["best_rank"] = pd.to_numeric(archive["best_rank"], errors="coerce")
        archive["best_rank"] = archive[["best_rank", "final_rank"]].min(axis=1, skipna=True)
    else:
        archive["best_rank"] = archive["final_rank"]
    if "best_rank_history" in archive.columns:
        archive["best_rank_history"] = pd.to_numeric(archive["best_rank_history"], errors="coerce")
        archive["best_rank"] = archive[["best_rank", "best_rank_history"]].min(axis=1, skipna=True)

    if "best_trend_score" in archive.columns:
        archive["best_trend_score"] = pd.to_numeric(archive["best_trend_score"], errors="coerce")
        archive["best_trend_score"] = archive[["best_trend_score", "final_trend_score"]].max(axis=1, skipna=True)
    else:
        archive["best_trend_score"] = archive["final_trend_score"]
    if "best_trend_score_history" in archive.columns:
        archive["best_trend_score_history"] = pd.to_numeric(archive["best_trend_score_history"], errors="coerce")
        archive["best_trend_score"] = archive[["best_trend_score", "best_trend_score_history"]].max(axis=1, skipna=True)

    if "best_score_at" not in archive.columns:
        archive["best_score_at"] = ""
    archive["best_score_at"] = archive["best_score_at"].fillna(archive_now)
    archive.loc[archive["best_score_at"].astype(str).str.strip().isin(["", "nan", "NaT", "None"]), "best_score_at"] = archive_now
    if "best_score_at_history" in archive.columns:
        history_score_at = archive["best_score_at_history"]
        blank_score_at = archive["best_score_at"].astype(str).str.strip().isin(["", "nan", "NaT", "None", "<NA>"])
        archive.loc[blank_score_at & history_score_at.notna(), "best_score_at"] = history_score_at

    if "best_rank_at" not in archive.columns:
        archive["best_rank_at"] = pd.NA

    for count_col in ["top10_count", "top50_count", "top200_count", "chart_in_count"]:
        if count_col in archive.columns:
            archive[count_col] = pd.to_numeric(archive[count_col], errors="coerce").fillna(0).astype(int)

    peak_pairs = {
        "peak_play_count": "play_count",
        "peak_upvote_count": "upvote_count",
        "peak_comment_count": "comment_count",
        "peak_adjusted_comment_count": "adjusted_comment_count",
    }
    for peak_col, current_col in peak_pairs.items():
        current = pd.to_numeric(archive[current_col], errors="coerce") if current_col in archive.columns else pd.Series([pd.NA] * len(archive))
        if peak_col in archive.columns:
            prior = pd.to_numeric(archive[peak_col], errors="coerce")
            archive[peak_col] = pd.concat([prior, current], axis=1).max(axis=1, skipna=True)
        else:
            archive[peak_col] = current

    for col in get_archive_columns():
        if col not in archive.columns:
            archive[col] = pd.NA

    archive = archive[get_archive_columns()].copy()

    if os.path.exists(ARCHIVE_PATH):
        old = pd.read_csv(ARCHIVE_PATH)
    else:
        old = pd.DataFrame(columns=get_archive_columns())

    combined = pd.concat([old, archive], ignore_index=True)
    if "id" in combined.columns:
        combined["id"] = combined["id"].astype(str)
        combined = combined.drop_duplicates(subset=["id"], keep="last")

    combined = serialize_datetime_columns_for_csv(combined)
    combined = normalize_text_columns(combined)
    combined.to_csv(ARCHIVE_PATH, index=False, encoding="utf-8-sig")
    print(f"[archive] archived={len(archive)}, archive_rows={len(combined)} -> {ARCHIVE_PATH}")


def prune_old_songs_and_history(final_db):
    if KEEP_EXPIRED_SONGS_IN_DB:
        print("[prune] KEEP_EXPIRED_SONGS_IN_DB=1, keeping all songs in suno_songs; ranking eligibility is handled by payload/filter logic")
        return final_db

    if SONG_RETENTION_DAYS <= 0:
        return final_db

    if final_db.empty or "created_at" not in final_db.columns:
        return final_db

    final_db = final_db.copy()

    final_db["created_at_dt"] = pd.to_datetime(
        final_db["created_at"],
        errors="coerce",
        utc=True,
    )

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=SONG_RETENTION_DAYS)

    before = len(final_db)
    expired_mask = final_db["created_at_dt"].notna() & (final_db["created_at_dt"] < cutoff)
    expired_db = final_db[expired_mask].copy()
    active_db = final_db[~expired_mask].copy()

    if not expired_db.empty:
        hist_for_archive = load_history_for_archive()
        scored_db = score_songs_for_archive(final_db.drop(columns=["created_at_dt"], errors="ignore"), hist_for_archive)
        archive_expired_songs(expired_db.drop(columns=["created_at_dt"], errors="ignore"), scored_db)

    kept_ids = set(active_db["id"].dropna().astype(str))

    active_db = active_db.drop(columns=["created_at_dt"], errors="ignore")

    removed = before - len(active_db)

    print(
        f"[prune] SONG_RETENTION_DAYS={SONG_RETENTION_DAYS}, "
        f"before={before}, after={len(active_db)}, archived_removed_from_active={removed}"
    )

    if os.path.exists(HISTORY_PATH):
        hist = pd.read_csv(HISTORY_PATH)

        if not hist.empty and "id" in hist.columns:
            before_hist = len(hist)

            hist["id"] = hist["id"].astype(str)
            hist = hist[hist["id"].isin(kept_ids)].copy()

            hist = normalize_text_columns(hist, columns=["title", "handle"])
            hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

            print(
                f"[prune_history_by_song_id] before={before_hist}, "
                f"after={len(hist)}, removed={before_hist - len(hist)}"
            )

    prune_rank_history_by_active_ids(kept_ids)

    return active_db



def compute_next_check_at(row, now=None):
    now = now or utc_timestamp()
    tier = row.get("update_tier") or row.get("computed_update_tier") or compute_update_tier(row, now=now)
    hours = tier_refresh_hours(tier)

    fail_count = pd.to_numeric(pd.Series([row.get("fetch_fail_count")]), errors="coerce").fillna(0).iloc[0]
    if int(fail_count) >= FETCH_FAIL_BACKOFF_THRESHOLD and tier != "frozen":
        hours = max(hours, 24)
    if int(fail_count) >= FETCH_FAIL_FREEZE_THRESHOLD:
        hours = FROZEN_REFRESH_HOURS

    return (now + pd.Timedelta(hours=hours)).isoformat()


def mark_fetch_failure(row, err):
    failed = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    now_txt = now_iso()
    try:
        fail_count = int(float(failed.get("fetch_fail_count") or 0)) + 1
    except Exception:
        fail_count = 1

    failed["last_checked_at"] = now_txt
    failed["fetch_fail_count"] = fail_count
    failed["last_fetch_error"] = str(err or "fetch_failed")[:500]

    if fail_count >= FETCH_FAIL_FREEZE_THRESHOLD or any(x in str(err).lower() for x in ["404", "not found", "clip_not_found", "private", "deleted"]):
        failed["status"] = "frozen"
        failed["update_tier"] = "frozen"
    else:
        failed["status"] = failed.get("status") or "active"
        failed["update_tier"] = failed.get("update_tier") or compute_update_tier(failed)

    failed["next_check_at"] = compute_next_check_at(failed)
    return normalize_record_text(failed)


def apply_operational_tiering(final_db):
    if final_db is None or final_db.empty:
        return final_db
    out = final_db.copy()
    now = utc_timestamp()
    playlist_ids = get_playlist_referenced_ids() if UPDATE_TIERING_ENABLED else set()

    for col in ["status", "update_tier", "next_check_at", "fetch_fail_count", "last_fetch_error", "last_change_at", "playlist_ref_count", "comments_fetch_needed", "last_comment_fetch_at"]:
        if col not in out.columns:
            out[col] = ""

    out["playlist_ref_count"] = out["id"].astype(str).apply(lambda sid: "1" if sid in playlist_ids else "0")
    out["update_tier"] = out.apply(lambda r: compute_update_tier(r, now=now, playlist_ids=playlist_ids), axis=1)
    blank_status = out["status"].astype(str).str.strip().isin(["", "nan", "None", "<NA>"])
    out.loc[blank_status, "status"] = "active"

    def fill_next(row):
        existing = pd.to_datetime(row.get("next_check_at"), errors="coerce", utc=True)
        if pd.notna(existing) and existing > now:
            return row.get("next_check_at")
        return compute_next_check_at(row, now=now)

    out["next_check_at"] = out.apply(fill_next, axis=1)
    return out


def compact_history_if_needed(hist, high_res_days=None):
    if os.getenv("COMPACT_HISTORY", "1").strip().lower() in {"0", "false", "no", "off"}:
        return hist
    if hist is None or hist.empty or "checked_at" not in hist.columns or "id" not in hist.columns:
        return hist
    high_res_days = int(high_res_days or os.getenv("HISTORY_HIGH_RES_DAYS", "7"))
    out = hist.copy()
    out["checked_at_dt"] = pd.to_datetime(out["checked_at"], errors="coerce", utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=high_res_days)
    recent = out[out["checked_at_dt"].isna() | (out["checked_at_dt"] >= cutoff)].copy()
    old = out[out["checked_at_dt"].notna() & (out["checked_at_dt"] < cutoff)].copy()
    if old.empty:
        return out.drop(columns=["checked_at_dt"], errors="ignore")
    old["history_date"] = old["checked_at_dt"].dt.date.astype(str)
    old = old.sort_values("checked_at_dt").drop_duplicates(subset=["id", "history_date"], keep="last")
    combined = pd.concat([recent, old], ignore_index=True)
    before = len(hist)
    combined = combined.drop(columns=["checked_at_dt", "history_date"], errors="ignore")
    print(f"[history_compact] before={before}, after={len(combined)}, high_res_days={high_res_days}")
    return combined

def detail_field_report(db):
    print("[detail_check] start")

    for col in [
        "created_at",
        "lyrics",
        "prompt",
        "gpt_description_prompt",
        "display_tags",
        "audio_url",
        "image_url",
    ]:
        if col not in db.columns:
            print(f"[detail_check] missing {col}")
            continue

        s = db[col].astype(str).str.strip()
        valid = (~s.str.lower().isin(["", "nan", "none", "null", "<na>", "-"])).sum()
        print(f"[detail_check] {col}_valid={valid}/{len(db)}")


def main():
    ensure_data_files()

    db = pd.read_csv(DB_PATH)

    if not db.empty and "id" in db.columns:
        db["id"] = db["id"].astype(str)

    print(f"[load] db_rows={len(db)}")

    if FETCH_NEW_SONGS:
        songs, logs = fetch_public_new_songs()

        for line in logs:
            print(line)

        db, added_count, duplicate_count = add_new_songs_to_db(db, songs)
    else:
        songs = []
        added_count = 0
        duplicate_count = 0
        print("[new_songs] FETCH_NEW_SONGS=0, skipping new song discovery")

    # 기존 DB에 created_at이 비어 있어도 history에는 남아 있을 수 있으므로 업데이트 대상 선정 전에 복구한다.
    db = restore_created_at_from_history(db)

    print(
        f"[new_songs] discovered={len(songs)}, "
        f"added={added_count}, duplicates={duplicate_count}, db_rows={len(db)}"
    )

    update_target = choose_rows_to_update(db)

    updated_rows = []
    history_rows = []
    updated_ids = set()

    success = 0
    failed = 0

    for _, row in update_target.iterrows():
        song_id = str(row.get("id"))

        if not song_id or song_id == "nan":
            continue

        clip, err = fetch_song_public(song_id)

        if clip:
            new_row = flatten_song(
                clip,
                old_row=row,
                source=row.get("source") or "public_song_page",
            )

            updated_rows.append(new_row)
            history_rows.append(history_snapshot(new_row))
            updated_ids.add(song_id)
            success += 1

            print(
                f"[OK] {song_id} {new_row.get('title')} "
                f"created_at={new_row.get('created_at')} "
                f"lyrics={'yes' if not is_blank_value(new_row.get('lyrics')) else 'no'} "
                f"prompt={'yes' if not is_blank_value(new_row.get('prompt')) else 'no'} "
                f"gpt={'yes' if not is_blank_value(new_row.get('gpt_description_prompt')) else 'no'} "
                f"play={new_row.get('play_count')} "
                f"like={new_row.get('upvote_count')} "
                f"comment={new_row.get('comment_count')}"
            )
        else:
            failed += 1
            failed_row = mark_fetch_failure(row, err)
            updated_rows.append(failed_row)
            updated_ids.add(song_id)
            print(f"[FAIL] {song_id}: {err}")

        time.sleep(REQUEST_SLEEP_SECONDS)

    if updated_rows:
        updated_df = pd.DataFrame(updated_rows)

        db["id"] = db["id"].astype(str)
        rest = db[~db["id"].isin(updated_ids)].copy()

        final_db = pd.concat([updated_df, rest], ignore_index=True)
    else:
        final_db = db

    if "id" in final_db.columns:
        final_db["id"] = final_db["id"].astype(str)
        final_db = final_db.drop_duplicates(subset=["id"], keep="first")

    # 상세 페이지 업데이트 이후에도 created_at이 비어 있는 행은 history 기준으로 한 번 더 복구한다.
    final_db = restore_created_at_from_history(final_db)

    if "created_at" in final_db.columns:
        final_db["created_at_dt"] = pd.to_datetime(
            final_db["created_at"],
            errors="coerce",
            utc=True,
        )
        final_db = final_db.sort_values(
            "created_at_dt",
            ascending=False,
            na_position="last",
        )
        final_db = final_db.drop(columns=["created_at_dt"], errors="ignore")

    print(f"[before_prune] db_rows={len(final_db)}")

    final_db = prune_old_songs_and_history(final_db)

    print(f"[after_prune] db_rows={len(final_db)}")

    final_db = apply_operational_tiering(final_db)

    text_changes = mojibake_report(final_db)
    if text_changes:
        print(f"[text_normalize] db_mojibake_fixed={text_changes}")
    final_db = normalize_text_columns(final_db)

    detail_field_report(final_db)

    final_db = serialize_datetime_columns_for_csv(final_db)
    final_db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    check_db = pd.read_csv(DB_PATH)
    print(f"[save_check] db_rows_written={len(check_db)} -> {DB_PATH}")

    if history_rows:
        hist_new = pd.DataFrame(history_rows)

        if os.path.exists(HISTORY_PATH):
            hist_old = pd.read_csv(HISTORY_PATH)
            hist = pd.concat([hist_old, hist_new], ignore_index=True)
        else:
            hist = hist_new

        kept_ids = set(final_db["id"].dropna().astype(str))
        hist["id"] = hist["id"].astype(str)
        hist = hist[hist["id"].isin(kept_ids)].copy()
        hist = compact_history_if_needed(hist)

        hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

        check_hist = pd.read_csv(HISTORY_PATH)
        print(f"[save_check] history_rows_written={len(check_hist)} -> {HISTORY_PATH}")

    print(
        f"[done] new_added={added_count}, update_success={success}, "
        f"update_failed={failed}, db_rows={len(final_db)}, "
        f"history_added={len(history_rows)}"
    )


if __name__ == "__main__":
    main()
