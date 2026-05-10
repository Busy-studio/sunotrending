import os
import re
import sys
import time
import requests
import pandas as pd
from urllib.parse import urlparse

from scripts.update_public_song_pages import (
    ensure_data_files,
    fetch_song_public,
    flatten_song,
    history_snapshot,
)


DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"
MAX_AGE_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))
REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.5"))


UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def normalize_suno_url(url):
    url = str(url or "").strip()

    if not url:
        raise ValueError("Suno URL is empty.")

    parsed = urlparse(url)

    if parsed.scheme not in ["http", "https"]:
        raise ValueError("URL must start with http:// or https://")

    host = parsed.netloc.lower()

    if host not in ["suno.com", "www.suno.com"]:
        raise ValueError("Only suno.com links are allowed.")

    return url


def extract_uuid_from_url(url):
    m = UUID_RE.search(url)
    if m:
        return m.group(0)

    return None


def resolve_suno_song_id(url):
    url = normalize_suno_url(url)

    direct_id = extract_uuid_from_url(url)
    if direct_id:
        return direct_id

    parsed = urlparse(url)

    if not parsed.path.startswith("/s/"):
        raise ValueError("Supported links are /song/{uuid} or /s/{short_code}.")

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }

    r = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
    r.raise_for_status()

    final_url = r.url
    song_id = extract_uuid_from_url(final_url)

    if song_id:
        return song_id

    song_id = extract_uuid_from_url(r.text)

    if song_id:
        return song_id

    raise ValueError("Could not resolve /s/ link to a Suno song UUID.")


def load_db():
    ensure_data_files()

    if os.path.exists(DB_PATH):
        db = pd.read_csv(DB_PATH)
    else:
        db = pd.DataFrame()

    if not db.empty and "id" in db.columns:
        db["id"] = db["id"].astype(str)

    return db


def load_history():
    if os.path.exists(HISTORY_PATH):
        hist = pd.read_csv(HISTORY_PATH)
    else:
        hist = pd.DataFrame()

    if not hist.empty and "id" in hist.columns:
        hist["id"] = hist["id"].astype(str)

    return hist


def validate_created_at(new_row):
    created_at = pd.to_datetime(new_row.get("created_at"), errors="coerce", utc=True)

    if pd.isna(created_at):
        raise ValueError("created_at is missing or invalid.")

    now = pd.Timestamp.now(tz="UTC")
    age_days = (now - created_at).total_seconds() / 86400

    print(f"[manual_add] created_at={created_at} age_days={age_days:.3f}")

    if age_days > MAX_AGE_DAYS:
        raise ValueError(
            f"This song is older than {MAX_AGE_DAYS} days. age_days={age_days:.2f}"
        )

    return created_at


def upsert_song(db, new_row):
    song_id = str(new_row.get("id"))

    if not song_id or song_id == "nan":
        raise ValueError("new_row has no valid id.")

    new_df = pd.DataFrame([new_row])

    if db.empty:
        final_db = new_df
    else:
        if "id" not in db.columns:
            raise ValueError("DB has no id column.")

        db["id"] = db["id"].astype(str)
        rest = db[db["id"] != song_id].copy()
        final_db = pd.concat([new_df, rest], ignore_index=True)

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

    final_db = final_db.drop_duplicates(subset=["id"], keep="first")
    return final_db


def append_history(hist, new_row):
    snap = history_snapshot(new_row)
    hist_new = pd.DataFrame([snap])

    if hist is None or hist.empty:
        return hist_new

    return pd.concat([hist, hist_new], ignore_index=True)


def main():
    song_url = os.getenv("MANUAL_SUNO_URL", "").strip()

    if not song_url:
        print("[manual_add ERROR] MANUAL_SUNO_URL is empty.")
        sys.exit(1)

    print(f"[manual_add] input_url={song_url}")

    try:
        song_id = resolve_suno_song_id(song_url)
    except Exception as e:
        print(f"[manual_add ERROR] invalid Suno link: {e}")
        sys.exit(1)

    print(f"[manual_add] resolved_song_id={song_id}")

    db = load_db()
    hist = load_history()

    print(f"[manual_add] db_rows_before={len(db)}")
    print(f"[manual_add] history_rows_before={len(hist)}")

    old_row = None

    if not db.empty and "id" in db.columns:
        matched = db[db["id"].astype(str) == str(song_id)]
        if not matched.empty:
            old_row = matched.iloc[0]

    clip, err = fetch_song_public(song_id)

    if not clip:
        print(f"[manual_add ERROR] failed to fetch song: {err}")
        sys.exit(1)

    new_row = flatten_song(
        clip,
        old_row=old_row,
        source="manual_add",
    )

    validate_created_at(new_row)

    final_db = upsert_song(db, new_row)
    final_hist = append_history(hist, new_row)

    final_db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")
    final_hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

    check_db = pd.read_csv(DB_PATH)
    check_hist = pd.read_csv(HISTORY_PATH)

    print(f"[manual_add] db_rows_after={len(check_db)} -> {DB_PATH}")
    print(f"[manual_add] history_rows_after={len(check_hist)} -> {HISTORY_PATH}")
    print(
        f"[manual_add done] id={song_id} "
        f"title={new_row.get('title')} "
        f"play={new_row.get('play_count')} "
        f"like={new_row.get('upvote_count')} "
        f"comment={new_row.get('comment_count')}"
    )

    time.sleep(REQUEST_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
