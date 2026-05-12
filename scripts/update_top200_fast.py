import os
import json
import time
import random
import math
import requests
import pandas as pd
from ranking_core import add_growth_features as core_add_growth_features, filter_active as core_filter_active, score_songs as core_score_songs, serialize_datetime_columns_for_csv
from text_utils import clean_text, is_blank_value as text_is_blank_value, normalize_record_text, normalize_text_columns
from update_public_song_pages import (
    get_archive_columns,
    load_history_for_archive,
    score_songs_for_archive,
    archive_expired_songs,
)
from datetime import datetime, timezone

DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"
ARCHIVE_PATH = "data/suno_song_archive.csv"

REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.5"))
TOP_N_FAST_UPDATE = int(os.getenv("TOP_N_FAST_UPDATE", "200"))
SONG_RETENTION_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))

RETENTION_HOURS = 96

GROWTH_WINDOW_HOURS = int(os.getenv("GROWTH_WINDOW_HOURS", "3"))

PLAY_WEIGHT = float(os.getenv("PLAY_WEIGHT", "1.0"))
LIKE_WEIGHT = float(os.getenv("LIKE_WEIGHT", "3.0"))
COMMENT_WEIGHT = float(os.getenv("COMMENT_WEIGHT", "4.0"))
GROWTH_WEIGHT = float(os.getenv("GROWTH_WEIGHT", "1.5"))
FRESHNESS_WEIGHT = float(os.getenv("FRESHNESS_WEIGHT", "35.0"))
FRESHNESS_POWER = float(os.getenv("FRESHNESS_POWER", "1.35"))

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

def clean_text_field(value):
    if text_is_blank_value(value):
        return None
    if isinstance(value, (dict, list)):
        return None
    s = clean_text(value)
    return s or None

def flatten_song(song, old_row=None, source="top200_fast_update"):
    metadata = song.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    contest_ids = metadata.get("contest_ids")
    song_id = song.get("id")

    first_seen_at = None
    old_source = source

    if old_row is not None:
        try:
            first_seen_at = old_row.get("first_seen_at")
            old_source = old_row.get("source") or source
        except Exception:
            pass

    row = {
        "id": song_id,
        "title": song.get("title"),
        "handle": song.get("handle"),
        "display_name": song.get("display_name"),
        "user_id": song.get("user_id"),
        "created_at": song.get("created_at"),
        "first_seen_at": first_seen_at or now_iso(),
        "last_checked_at": now_iso(),

        "play_count": song.get("play_count"),
        "upvote_count": song.get("upvote_count"),
        "comment_count": song.get("comment_count"),
        "flag_count": song.get("flag_count"),

        "is_contest_clip": song.get("is_contest_clip"),
        "contest_ids": ", ".join(contest_ids) if isinstance(contest_ids, list) else contest_ids,
        "download_disabled_reason": song.get("download_disabled_reason"),

        "is_public": song.get("is_public"),
        "is_hidden": song.get("is_hidden"),
        "is_trashed": song.get("is_trashed"),
        "explicit": song.get("explicit"),

        "model": song.get("model_name") or metadata.get("model_name") or song.get("major_model_version"),
        "major_model_version": song.get("major_model_version"),
        "display_tags": song.get("display_tags") or metadata.get("tags"),
        "duration": metadata.get("duration"),

        # 상세 페이지에서 가져올 수 있는 가사/프롬프트 후보
        "lyrics": (
            clean_text_field(song.get("lyrics"))
            or clean_text_field(metadata.get("lyrics"))
            or clean_text_field(metadata.get("lyric"))
        ),
        "prompt": (
            clean_text_field(song.get("prompt"))
            or clean_text_field(metadata.get("prompt"))
        ),
        "gpt_description_prompt": (
            clean_text_field(song.get("gpt_description_prompt"))
            or clean_text_field(metadata.get("gpt_description_prompt"))
        ),

        "song_url": f"https://suno.com/song/{song_id}" if song_id else None,
        "audio_url": song.get("audio_url"),
        "image_url": song.get("image_url"),
        "source": old_source,
    }

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


def prepare_db_for_scoring(db):
    db = db.copy()

    if "id" in db.columns:
        db["id"] = db["id"].astype(str)

    for col in ["created_at", "first_seen_at", "last_checked_at"]:
        if col in db.columns:
            db[col] = pd.to_datetime(db[col], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col in db.columns:
            db[col] = pd.to_numeric(db[col], errors="coerce").fillna(0)
        else:
            db[col] = 0

    return db


def prepare_history_for_scoring(hist):
    if hist is None or hist.empty:
        return pd.DataFrame()

    hist = hist.copy()

    if "id" in hist.columns:
        hist["id"] = hist["id"].astype(str)

    if "checked_at" in hist.columns:
        hist["checked_at"] = pd.to_datetime(hist["checked_at"], errors="coerce", utc=True)

    if "created_at" in hist.columns:
        hist["created_at"] = pd.to_datetime(hist["created_at"], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col in hist.columns:
            hist[col] = pd.to_numeric(hist[col], errors="coerce").fillna(0)

    return hist


def add_growth_features(db, hist, window_hours):
    """Compatibility wrapper; scoring lives in ranking_core."""
    return core_add_growth_features(db, hist, window_hours)


def score_songs(db, hist):
    """Compatibility wrapper; scoring lives in ranking_core."""
    return core_score_songs(db, hist)

def filter_recent_and_noncontest(df):
    view = df.copy()

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=SONG_RETENTION_DAYS)

    if "created_at" in view.columns:
        view = view[view["created_at"].isna() | (view["created_at"] >= cutoff)]

    if "is_contest_clip" in view.columns:
        view = view[view["is_contest_clip"].astype(str).str.lower() != "true"]

    if "download_disabled_reason" in view.columns:
        view = view[view["download_disabled_reason"].astype(str) != "remix_contest"]

    if "contest_ids" in view.columns:
        contest_str = view["contest_ids"].astype(str).str.strip().str.lower()
        view = view[
            view["contest_ids"].isna()
            | (contest_str == "")
            | (contest_str == "nan")
            | (contest_str == "none")
        ]

    return view


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
        scored_db = score_songs_for_archive(
            final_db.drop(columns=["created_at_dt"], errors="ignore"),
            hist_for_archive,
        )
        archive_expired_songs(
            expired_db.drop(columns=["created_at_dt"], errors="ignore"),
            scored_db,
        )

    kept_ids = set(active_db["id"].dropna().astype(str))
    active_db = active_db.drop(columns=["created_at_dt"], errors="ignore")

    print(
        f"[prune] SONG_RETENTION_DAYS={SONG_RETENTION_DAYS}, "
        f"before={before}, after={len(active_db)}, archived_removed_from_active={before - len(active_db)}"
    )

    if os.path.exists(HISTORY_PATH):
        hist = pd.read_csv(HISTORY_PATH)

        if not hist.empty and "id" in hist.columns:
            before_hist = len(hist)

            hist["id"] = hist["id"].astype(str)
            hist = hist[hist["id"].isin(kept_ids)].copy()

            hist = normalize_text_columns(hist, columns=["title", "handle"])
            hist = serialize_datetime_columns_for_csv(hist, columns=["checked_at", "created_at"])
            hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

            print(
                f"[prune_history_by_song_id] before={before_hist}, "
                f"after={len(hist)}, removed={before_hist - len(hist)}"
            )

    return active_db


def append_history(history_rows, final_db):
    if not history_rows:
        return 0

    hist_new = pd.DataFrame(history_rows)

    if os.path.exists(HISTORY_PATH):
        hist_old = pd.read_csv(HISTORY_PATH)
        hist = pd.concat([hist_old, hist_new], ignore_index=True)
    else:
        hist = hist_new

    kept_ids = set(final_db["id"].dropna().astype(str))

    if "id" in hist.columns:
        hist["id"] = hist["id"].astype(str)
        hist = hist[hist["id"].isin(kept_ids)].copy()

    hist = normalize_text_columns(hist, columns=["title", "handle"])
    hist = serialize_datetime_columns_for_csv(hist, columns=["checked_at", "created_at"])
    hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

    return len(history_rows)


def main():
    ensure_data_files()

    db_raw = pd.read_csv(DB_PATH)

    if db_raw.empty or "id" not in db_raw.columns:
        print("[fast] DB is empty. Nothing to update.")
        return

    db_for_score = prepare_db_for_scoring(db_raw)

    if os.path.exists(HISTORY_PATH):
        hist_raw = pd.read_csv(HISTORY_PATH)
    else:
        hist_raw = pd.DataFrame()

    hist = prepare_history_for_scoring(hist_raw)

    scored = core_score_songs(db_for_score, hist)
    scored = core_filter_active(scored, max_age_days=SONG_RETENTION_DAYS, hide_contest=True)

    top = scored.sort_values(
        "trend_score",
        ascending=False,
        na_position="last",
    ).head(TOP_N_FAST_UPDATE).copy()

    target_ids = top["id"].dropna().astype(str).tolist()

    print(f"[fast] db_rows={len(db_raw)}, target_top_n={len(target_ids)}")

    updated_rows = []
    history_rows = []
    updated_ids = set()

    success = 0
    failed = 0

    db_raw["id"] = db_raw["id"].astype(str)

    for song_id in target_ids:
        old_match = db_raw[db_raw["id"] == song_id]

        if old_match.empty:
            continue

        old_row = old_match.iloc[0]

        clip, err = fetch_song_public(song_id)

        if clip:
            new_row = flatten_song(clip, old_row=old_row, source=old_row.get("source") or "top200_fast_update")
            updated_rows.append(new_row)
            history_rows.append(history_snapshot(new_row))
            updated_ids.add(song_id)
            success += 1

            print(
                f"[OK] {song_id} {new_row.get('title')} "
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
        rest = db_raw[~db_raw["id"].isin(updated_ids)].copy()
        final_db = pd.concat([updated_df, rest], ignore_index=True)
    else:
        final_db = db_raw

    if "created_at" in final_db.columns:
        final_db["created_at_dt"] = pd.to_datetime(final_db["created_at"], errors="coerce", utc=True)
        final_db = final_db.sort_values("created_at_dt", ascending=False, na_position="last")
        final_db = final_db.drop(columns=["created_at_dt"], errors="ignore")

    final_db = prune_old_songs_and_history(final_db)

    final_db = normalize_text_columns(final_db)
    final_db = serialize_datetime_columns_for_csv(final_db)
    final_db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    history_added = append_history(history_rows, final_db)

    print(
        f"[fast_done] update_success={success}, update_failed={failed}, "
        f"db_rows={len(final_db)}, history_added={history_added}"
    )


if __name__ == "__main__":
    main()
