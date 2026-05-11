import os
import json
import time
import random
import math
import requests
import pandas as pd
from datetime import datetime, timezone

DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"
ARCHIVE_PATH = "data/suno_song_archive.csv"

REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "1.2"))
MAX_UPDATE_ROWS = int(os.getenv("MAX_UPDATE_ROWS", "1000"))

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


def get_archive_columns():
    return [
        "archived_at", "archive_reason",
        "id", "title", "handle", "display_name", "user_id",
        "created_at", "first_seen_at", "last_checked_at",
        "play_count", "upvote_count", "comment_count", "adjusted_comment_count",
        "comment_quality_ratio", "meaningful_count", "generic_count",
        "mention_only_count", "emoji_only_count", "flag_count",
        "final_rank", "best_rank",
        "final_trend_score", "final_base_score", "final_growth_score", "final_freshness_score",
        "best_trend_score", "best_score_at",
        "peak_play_count", "peak_upvote_count", "peak_comment_count", "peak_adjusted_comment_count",
        "model", "major_model_version", "display_tags", "duration",
        "lyrics", "prompt", "gpt_description_prompt",
        "song_url", "audio_url", "image_url", "source",
    ]


def is_blank_value(value):
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except Exception:
        pass

    if isinstance(value, (dict,)):
        return True

    if isinstance(value, list):
        return len(value) == 0

    s = str(value).strip()

    if not s:
        return True

    if s.lower() in ["nan", "none", "null", "undefined", "<na>", "-"]:
        return True

    # Next.js / RSC 참조 토큰 제거: $5b, $12, $abc 같은 값
    if s.startswith("$") and len(s) <= 8:
        return True

    return False


def clean_text_field(value):
    if is_blank_value(value):
        return None

    if isinstance(value, (dict, list)):
        return None

    return str(value).strip()


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
    if is_blank_value(value):
        return None

    if isinstance(value, list):
        cleaned = [str(x).strip() for x in value if not is_blank_value(x)]
        return ", ".join(cleaned) if cleaned else None

    return str(value).strip()


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

    return {
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
    }


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


def choose_rows_to_update(db):
    if db.empty:
        return db

    out = db.copy()

    if "created_at" in out.columns:
        out["created_at_dt"] = pd.to_datetime(out["created_at"], errors="coerce", utc=True)

        # created_at이 비어 있는 곡은 상세 페이지 재조회 기회가 없으면 계속 Top 200 후보에서 빠질 수 있다.
        # missing-created 곡을 먼저 업데이트하고, 나머지는 최신 생성순으로 업데이트한다.
        missing_created = out["created_at_dt"].isna()
        missing_part = out[missing_created].copy()
        normal_part = out[~missing_created].sort_values("created_at_dt", ascending=False, na_position="last").copy()
        out = pd.concat([missing_part, normal_part], ignore_index=True)
        print(
            f"[choose_update] max={MAX_UPDATE_ROWS}, "
            f"missing_created={int(missing_created.sum())}, normal={int((~missing_created).sum())}"
        )
    else:
        print(f"[choose_update] created_at column missing, taking first {MAX_UPDATE_ROWS}")

    return out.head(MAX_UPDATE_ROWS).drop(columns=["created_at_dt"], errors="ignore").copy()


def restore_created_at_from_history(db):
    """Fill missing active DB created_at from history snapshots."""
    if db is None or db.empty:
        return db

    if not os.path.exists(HISTORY_PATH):
        print("[restore_created_at] skipped: history file missing")
        return db

    if "id" not in db.columns:
        print("[restore_created_at] skipped: db id column missing")
        return db

    try:
        hist = pd.read_csv(HISTORY_PATH)
    except Exception as e:
        print(f"[restore_created_at] skipped: failed to read history: {e}")
        return db

    if hist.empty or "id" not in hist.columns or "created_at" not in hist.columns:
        print("[restore_created_at] skipped: no usable history created_at")
        return db

    db = db.copy()
    if "created_at" not in db.columns:
        db["created_at"] = pd.NA

    db["id"] = db["id"].astype(str)
    hist["id"] = hist["id"].astype(str)

    db_created = pd.to_datetime(db["created_at"], errors="coerce", utc=True)
    before_valid = int(db_created.notna().sum())

    hist_created = pd.to_datetime(hist["created_at"], errors="coerce", utc=True)
    hist = hist.assign(__created_at_dt=hist_created).dropna(subset=["__created_at_dt"])
    if hist.empty:
        print("[restore_created_at] skipped: all history created_at invalid")
        return db

    created_map = hist.groupby("id")["__created_at_dt"].min()
    missing = db_created.isna()
    restored = db.loc[missing, "id"].map(created_map)
    has_restored = restored.notna()
    restored_count = int(has_restored.sum())

    if restored_count:
        restored_values = restored[has_restored].dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
        db.loc[missing & has_restored, "created_at"] = restored_values

    after_valid = int(pd.to_datetime(db["created_at"], errors="coerce", utc=True).notna().sum())
    print(
        f"[restore_created_at] valid_before={before_valid}/{len(db)}, "
        f"restored={restored_count}, valid_after={after_valid}/{len(db)}"
    )

    return db


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
    db = db.copy()

    for col in ["play_delta_window", "upvote_delta_window", "comment_delta_window"]:
        db[col] = 0.0

    if hist.empty or "id" not in hist.columns or "checked_at" not in hist.columns:
        return db

    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(hours=window_hours)
    recent = hist[hist["checked_at"] >= cutoff].copy()
    if recent.empty:
        return db

    rows = []
    for song_id, g in recent.groupby("id"):
        g = g.sort_values("checked_at")
        if len(g) < 2:
            continue
        first = g.iloc[0]
        last = g.iloc[-1]
        rows.append({
            "id": str(song_id),
            "play_delta_window": max(0, float(last.get("play_count", 0)) - float(first.get("play_count", 0))),
            "upvote_delta_window": max(0, float(last.get("upvote_count", 0)) - float(first.get("upvote_count", 0))),
            "comment_delta_window": max(0, float(last.get("comment_count", 0)) - float(first.get("comment_count", 0))),
        })

    if not rows:
        return db

    growth = pd.DataFrame(rows)
    db = db.merge(growth, on="id", how="left", suffixes=("", "_growth"))

    for col in ["play_delta_window", "upvote_delta_window", "comment_delta_window"]:
        growth_col = f"{col}_growth"
        if growth_col in db.columns:
            db[col] = db[growth_col].fillna(db[col])
            db = db.drop(columns=[growth_col], errors="ignore")
        db[col] = db[col].fillna(0)

    return db


def score_songs_for_archive(db, hist):
    view = db.copy()
    now = pd.Timestamp.now(tz="UTC")

    if "id" in view.columns:
        view["id"] = view["id"].astype(str)

    if "created_at" not in view.columns:
        view["created_at"] = pd.NaT
    view["created_at_dt"] = pd.to_datetime(view["created_at"], errors="coerce", utc=True)

    view["age_hours"] = (now - view["created_at_dt"]).dt.total_seconds() / 3600
    view["age_hours"] = view["age_hours"].clip(lower=0)
    view["remaining_hours"] = (RETENTION_HOURS - view["age_hours"]).clip(lower=0)
    view["freshness"] = (view["remaining_hours"] / RETENTION_HOURS).clip(lower=0, upper=1)
    view["freshness_score"] = (view["freshness"] ** FRESHNESS_POWER) * FRESHNESS_WEIGHT

    view = add_growth_features_for_archive(view, hist, GROWTH_WINDOW_HOURS)

    for col in ["play_count", "upvote_count", "comment_count"]:
        if col not in view.columns:
            view[col] = 0
        view[col] = to_number(view[col])

    if "adjusted_comment_count" in view.columns:
        view["effective_comment_count"] = pd.to_numeric(view["adjusted_comment_count"], errors="coerce")
        view["effective_comment_count"] = view["effective_comment_count"].fillna(view["comment_count"])
    else:
        view["effective_comment_count"] = view["comment_count"]

    view["effective_comment_count"] = view["effective_comment_count"].clip(lower=0)

    view["base_score"] = (
        PLAY_WEIGHT * view["play_count"].apply(lambda x: math.log1p(max(0, x)))
        + LIKE_WEIGHT * view["upvote_count"].apply(lambda x: math.log1p(max(0, x)))
        + COMMENT_WEIGHT * view["effective_comment_count"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score_raw"] = (
        0.4 * view["play_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 2.0 * view["upvote_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 3.0 * view["comment_delta_window"].apply(lambda x: math.log1p(max(0, x)))
    )
    view["growth_score"] = view["growth_score_raw"] * GROWTH_WEIGHT
    view["trend_score"] = view["base_score"] + view["growth_score"] + view["freshness_score"]

    ranked = view.sort_values("trend_score", ascending=False, na_position="last").copy()
    ranked["computed_rank"] = range(1, len(ranked) + 1)

    return ranked


def archive_expired_songs(expired_db, scored_db):
    if expired_db.empty:
        return

    archive_now = now_iso()
    expired = expired_db.copy()
    expired["id"] = expired["id"].astype(str)

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

    if "best_trend_score" in archive.columns:
        archive["best_trend_score"] = pd.to_numeric(archive["best_trend_score"], errors="coerce")
        archive["best_trend_score"] = archive[["best_trend_score", "final_trend_score"]].max(axis=1, skipna=True)
    else:
        archive["best_trend_score"] = archive["final_trend_score"]

    if "best_score_at" not in archive.columns:
        archive["best_score_at"] = ""
    archive["best_score_at"] = archive["best_score_at"].fillna(archive_now)
    archive.loc[archive["best_score_at"].astype(str).str.strip().isin(["", "nan", "NaT", "None"]), "best_score_at"] = archive_now

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

    combined.to_csv(ARCHIVE_PATH, index=False, encoding="utf-8-sig")
    print(f"[archive] archived={len(archive)}, archive_rows={len(combined)} -> {ARCHIVE_PATH}")


def prune_old_songs_and_history(final_db):
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

            hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

            print(
                f"[prune_history_by_song_id] before={before_hist}, "
                f"after={len(hist)}, removed={before_hist - len(hist)}"
            )

    return active_db


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

    songs, logs = fetch_public_new_songs()

    for line in logs:
        print(line)

    db, added_count, duplicate_count = add_new_songs_to_db(db, songs)

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

    detail_field_report(final_db)

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
