import os
import json
import time
import random
import requests
import pandas as pd
from datetime import datetime, timezone

DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"

REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "1.2"))
MAX_UPDATE_ROWS = int(os.getenv("MAX_UPDATE_ROWS", "1000"))

# 무로그인 new_songs는 page_size 50까지 가능, 100은 서버가 거절함
NEW_SONGS_PAGES = int(os.getenv("NEW_SONGS_PAGES", "3"))
NEW_SONGS_PAGE_SIZE = int(os.getenv("NEW_SONGS_PAGE_SIZE", "50"))

# 단기 트렌딩용: Suno created_at 기준 N일 지난 곡은 DB/history에서 삭제
SONG_RETENTION_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))

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

def clean_text_field(value):
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return None

    s = str(value).strip()

    if not s:
        return None

    if s.lower() in ["nan", "none", "null", "undefined"]:
        return None

    # Next.js / RSC 참조 토큰 제거: $5b, $12, $abc 같은 값
    if s.startswith("$") and len(s) <= 8:
        return None

    return s


def flatten_song(song, old_row=None, source="public"):
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
                    continue

                page_songs.append(song)

            found.extend(page_songs)

            logs.append(
                f"[new_songs] page={page_idx + 1}, cursor={cursor}, "
                f"page_size={NEW_SONGS_PAGE_SIZE}, raw_items={len(items)}, "
                f"songs={len(page_songs)}, contest_excluded={contest_count}, "
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
    if db.empty:
        existing_ids = set()
    else:
        existing_ids = set(db["id"].dropna().astype(str))

    new_rows = []
    duplicate_count = 0

    for song in songs:
        song_id = str(song.get("id"))

        if not song_id or song_id == "None":
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
        out = out.sort_values("created_at_dt", ascending=False, na_position="last")

    return out.head(MAX_UPDATE_ROWS).copy()


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

    removed = before - len(final_db)

    print(
        f"[prune] SONG_RETENTION_DAYS={SONG_RETENTION_DAYS}, "
        f"before={before}, after={len(final_db)}, removed={removed}"
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
            new_row = flatten_song(clip, old_row=row, source=row.get("source") or "public_song_page")
            updated_rows.append(new_row)
            history_rows.append(history_snapshot(new_row))
            updated_ids.add(song_id)
            success += 1
            print(
                f"[OK] {song_id} {new_row.get('title')} "
                f"created_at={new_row.get('created_at')} "
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

    if "created_at" in final_db.columns:
        final_db["created_at_dt"] = pd.to_datetime(final_db["created_at"], errors="coerce", utc=True)
        final_db = final_db.sort_values("created_at_dt", ascending=False, na_position="last")
        final_db = final_db.drop(columns=["created_at_dt"], errors="ignore")

    final_db = prune_old_songs_and_history(final_db)

    final_db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")

    if history_rows:
        hist_new = pd.DataFrame(history_rows)

        if os.path.exists(HISTORY_PATH):
            hist_old = pd.read_csv(HISTORY_PATH)
            hist = pd.concat([hist_old, hist_new], ignore_index=True)
        else:
            hist = hist_new

        # 혹시 prune 이후 삭제된 곡이 있으면 history도 최종 DB 기준으로 한 번 더 정리
        kept_ids = set(final_db["id"].dropna().astype(str))
        hist["id"] = hist["id"].astype(str)
        hist = hist[hist["id"].isin(kept_ids)].copy()

        hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")

    print(
        f"[done] new_added={added_count}, update_success={success}, "
        f"update_failed={failed}, db_rows={len(final_db)}, "
        f"history_added={len(history_rows)}"
    )


if __name__ == "__main__":
    main()
