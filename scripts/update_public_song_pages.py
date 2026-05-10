import os
import json
import random
import time
import requests
import pandas as pd
from datetime import datetime, timezone

DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"

REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "1.2"))
MAX_UPDATE_ROWS = int(os.getenv("MAX_UPDATE_ROWS", "1000"))

PUBLIC_HEADERS = {
    "accept": "*/*",
    "accept-language": "ko,en-US;q=0.9,en;q=0.8",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
    "referer": "https://suno.com/explore",
    "rsc": "1",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_balanced_json_object(text: str, start_index: int) -> str | None:
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


def extract_clip_from_rsc_text(text: str) -> dict | None:
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


def fetch_song_public(song_id: str) -> tuple[dict | None, str]:
    rsc_key = f"rsc{random.randint(100000, 999999)}"
    url = f"https://suno.com/song/{song_id}?_rsc={rsc_key}"

    try:
        r = requests.get(url, headers=PUBLIC_HEADERS, timeout=30)
    except Exception as exc:
        return None, f"request_error:{exc}"

    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"

    clip = extract_clip_from_rsc_text(r.text)
    if not clip:
        return None, "clip_not_found"

    return clip, ""


def flatten_song(song: dict, old_row: dict | pd.Series | None = None) -> dict:
    metadata = song.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    contest_ids = metadata.get("contest_ids")
    song_id = song.get("id")

    first_seen_at = None
    source = "public_song_page"

    if old_row is not None:
        try:
            first_seen_at = old_row.get("first_seen_at")
            source = old_row.get("source") or source
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
        "source": source,
    }


def history_snapshot(row: dict) -> dict:
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


def ensure_data_files() -> None:
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(DB_PATH):
        pd.DataFrame(columns=[
            "id", "title", "handle", "display_name", "user_id", "created_at",
            "first_seen_at", "last_checked_at", "play_count", "upvote_count",
            "comment_count", "flag_count", "is_contest_clip", "contest_ids",
            "download_disabled_reason", "is_public", "is_hidden", "is_trashed",
            "explicit", "model", "major_model_version", "display_tags", "duration",
            "song_url", "audio_url", "image_url", "source",
        ]).to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    if not os.path.exists(HISTORY_PATH):
        pd.DataFrame(columns=[
            "checked_at", "id", "title", "handle", "created_at",
            "play_count", "upvote_count", "comment_count", "flag_count",
        ]).to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")


def main() -> None:
    ensure_data_files()

    db_original = pd.read_csv(DB_PATH)
    if db_original.empty or "id" not in db_original.columns:
        print("DB is empty or id column missing. Nothing to update.")
        return

    db_original["id"] = db_original["id"].astype(str)
    work = db_original.copy()

    if "last_checked_at" in work.columns:
        work["last_checked_at_dt"] = pd.to_datetime(work["last_checked_at"], errors="coerce", utc=True)
        # Oldest checked first, so every song eventually gets refreshed.
        work = work.sort_values("last_checked_at_dt", ascending=True, na_position="first")
    elif "created_at" in work.columns:
        work["created_at_dt"] = pd.to_datetime(work["created_at"], errors="coerce", utc=True)
        work = work.sort_values("created_at_dt", ascending=False, na_position="last")

    work = work.head(MAX_UPDATE_ROWS).copy()

    updated_rows = []
    history_rows = []
    success = 0
    failed = 0

    for _, row in work.iterrows():
        song_id = str(row["id"])
        clip, err = fetch_song_public(song_id)

        if clip:
            new_row = flatten_song(clip, old_row=row)
            updated_rows.append(new_row)
            history_rows.append(history_snapshot(new_row))
            success += 1
            print(
                f"[OK] {song_id} | {new_row.get('title')} | "
                f"play={new_row.get('play_count')} like={new_row.get('upvote_count')} comment={new_row.get('comment_count')}"
            )
        else:
            old = row.drop(labels=["created_at_dt", "last_checked_at_dt"], errors="ignore").to_dict()
            old["last_checked_at"] = row.get("last_checked_at")
            updated_rows.append(old)
            failed += 1
            print(f"[FAIL] {song_id}: {err}")

        time.sleep(REQUEST_SLEEP_SECONDS)

    updated_df = pd.DataFrame(updated_rows)

    updated_ids = set(updated_df["id"].dropna().astype(str)) if not updated_df.empty else set()
    rest = db_original[~db_original["id"].astype(str).isin(updated_ids)].copy()
    final_db = pd.concat([updated_df, rest], ignore_index=True)

    if "created_at" in final_db.columns:
        final_db["created_at_dt"] = pd.to_datetime(final_db["created_at"], errors="coerce", utc=True)
        final_db = final_db.sort_values("created_at_dt", ascending=False, na_position="last")
        final_db = final_db.drop(columns=["created_at_dt"], errors="ignore")

    final_db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    if history_rows:
        hist_new = pd.DataFrame(history_rows)
        if os.path.exists(HISTORY_PATH):
            hist_old = pd.read_csv(HISTORY_PATH)
            hist = pd.concat([hist_old, hist_new], ignore_index=True)
        else:
            hist = hist_new
        hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

    print(f"Done. success={success}, failed={failed}, db_rows={len(final_db)}, history_added={len(history_rows)}")


if __name__ == "__main__":
    main()
