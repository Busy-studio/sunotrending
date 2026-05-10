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

REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.5"))
TOP_N_FAST_UPDATE = int(os.getenv("TOP_N_FAST_UPDATE", "200"))
SONG_RETENTION_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))

RETENTION_HOURS = 96

GROWTH_WINDOW_HOURS = int(os.getenv("GROWTH_WINDOW_HOURS", "3"))

PLAY_WEIGHT = float(os.getenv("PLAY_WEIGHT", "1.0"))
LIKE_WEIGHT = float(os.getenv("LIKE_WEIGHT", "3.0"))
COMMENT_WEIGHT = float(os.getenv("COMMENT_WEIGHT", "4.0"))
GROWTH_WEIGHT = float(os.getenv("GROWTH_WEIGHT", "2.5"))
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
            "song_url", "audio_url", "image_url", "source",
        ]).to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    if not os.path.exists(HISTORY_PATH):
        pd.DataFrame(columns=[
            "checked_at", "id", "title", "handle", "created_at",
            "play_count", "upvote_count", "comment_count", "flag_count",
        ]).to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")


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

    return {
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

        "song_url": f"https://suno.com/song/{song_id}" if song_id else None,
        "audio_url": song.get("audio_url"),
        "image_url": song.get("image_url"),
        "source": old_source,
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
    db = db.copy()

    for col in [
        "play_delta_window",
        "upvote_delta_window",
        "comment_delta_window",
        "play_velocity_per_hour",
        "upvote_velocity_per_hour",
        "comment_velocity_per_hour",
    ]:
        db[col] = 0.0

    if hist.empty or "id" not in hist.columns or "checked_at" not in hist.columns:
        return db

    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(hours=window_hours)

    recent = hist[hist["checked_at"] >= cutoff].copy()

    if recent.empty:
        return db

    agg_rows = []

    for song_id, g in recent.groupby("id"):
        g = g.sort_values("checked_at")

        if len(g) < 2:
            continue

        first = g.iloc[0]
        last = g.iloc[-1]

        hours = (last["checked_at"] - first["checked_at"]).total_seconds() / 3600

        if hours <= 0:
            hours = max(window_hours, 1)

        play_delta = max(0, float(last.get("play_count", 0)) - float(first.get("play_count", 0)))
        upvote_delta = max(0, float(last.get("upvote_count", 0)) - float(first.get("upvote_count", 0)))
        comment_delta = max(0, float(last.get("comment_count", 0)) - float(first.get("comment_count", 0)))

        agg_rows.append({
            "id": str(song_id),
            "play_delta_window": play_delta,
            "upvote_delta_window": upvote_delta,
            "comment_delta_window": comment_delta,
            "play_velocity_per_hour": play_delta / hours,
            "upvote_velocity_per_hour": upvote_delta / hours,
            "comment_velocity_per_hour": comment_delta / hours,
        })

    if not agg_rows:
        return db

    growth = pd.DataFrame(agg_rows)
    db = db.merge(growth, on="id", how="left", suffixes=("", "_growth"))

    for col in [
        "play_delta_window",
        "upvote_delta_window",
        "comment_delta_window",
        "play_velocity_per_hour",
        "upvote_velocity_per_hour",
        "comment_velocity_per_hour",
    ]:
        if col in db.columns:
            db[col] = db[col].fillna(0)

    return db


def score_songs(db, hist):
    view = db.copy()

    now = pd.Timestamp.now(tz="UTC")

    if "created_at" not in view.columns:
        view["created_at"] = pd.NaT

    view["age_hours"] = (now - view["created_at"]).dt.total_seconds() / 3600
    view["age_hours"] = view["age_hours"].clip(lower=0)

    view["remaining_hours"] = (RETENTION_HOURS - view["age_hours"]).clip(lower=0)

    view["freshness"] = (view["remaining_hours"] / RETENTION_HOURS).clip(lower=0, upper=1)
    view["freshness_score"] = (view["freshness"] ** FRESHNESS_POWER) * FRESHNESS_WEIGHT

    view = add_growth_features(view, hist, GROWTH_WINDOW_HOURS)

    view["base_score"] = (
        PLAY_WEIGHT * view["play_count"].apply(lambda x: math.log1p(max(0, x)))
        + LIKE_WEIGHT * view["upvote_count"].apply(lambda x: math.log1p(max(0, x)))
        + COMMENT_WEIGHT * view["comment_count"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score_raw"] = (
        1.2 * view["play_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 5.0 * view["upvote_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 8.0 * view["comment_delta_window"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score"] = view["growth_score_raw"] * GROWTH_WEIGHT

    view["trend_score"] = (
        view["base_score"]
        + view["growth_score"]
        + view["freshness_score"]
    )

    return view


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

    final_db = final_db[
        final_db["created_at_dt"].isna()
        | (final_db["created_at_dt"] >= cutoff)
    ].copy()

    kept_ids = set(final_db["id"].dropna().astype(str))

    final_db = final_db.drop(columns=["created_at_dt"], errors="ignore")

    print(
        f"[prune] SONG_RETENTION_DAYS={SONG_RETENTION_DAYS}, "
        f"before={before}, after={len(final_db)}, removed={before - len(final_db)}"
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

    return final_db


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

    scored = score_songs(db_for_score, hist)
    scored = filter_recent_and_noncontest(scored)

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

    final_db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    history_added = append_history(history_rows, final_db)

    print(
        f"[fast_done] update_success={success}, update_failed={failed}, "
        f"db_rows={len(final_db)}, history_added={history_added}"
    )


if __name__ == "__main__":
    main()
