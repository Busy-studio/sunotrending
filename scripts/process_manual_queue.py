import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.manual_add_song import (
    DB_PATH,
    HISTORY_PATH,
    resolve_suno_song_id,
    load_db,
    load_history,
    validate_created_at,
    upsert_song,
    append_history,
)

from scripts.update_public_song_pages import (
    fetch_song_public,
    flatten_song,
)


QUEUE_PATH = "data/manual_song_queue.csv"
MAX_QUEUE_ITEMS = int(os.getenv("MANUAL_QUEUE_MAX_ITEMS", "20"))
REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.5"))


QUEUE_COLUMNS = [
    "request_id",
    "submitted_at",
    "submitted_by_user_key",
    "submitted_by_email_hash",
    "submitted_by_name",
    "url",
    "status",
    "song_id",
    "title",
    "processed_at",
    "error",
]


def load_queue():
    if not os.path.exists(QUEUE_PATH):
        q = pd.DataFrame(columns=QUEUE_COLUMNS)
    else:
        q = pd.read_csv(
            QUEUE_PATH,
            dtype=str,
            keep_default_na=False,
        )

    for col in QUEUE_COLUMNS:
        if col not in q.columns:
            q[col] = ""

    q = q[QUEUE_COLUMNS].copy()

    for col in QUEUE_COLUMNS:
        q[col] = q[col].fillna("").astype(str)

    return q


def save_queue(q):
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)

    q = q.copy()

    for col in QUEUE_COLUMNS:
        if col not in q.columns:
            q[col] = ""

    q = q[QUEUE_COLUMNS].copy()

    for col in QUEUE_COLUMNS:
        q[col] = q[col].fillna("").astype(str)

    q.to_csv(QUEUE_PATH, index=False, encoding="utf-8-sig")


def is_pending_status(value):
    s = str(value or "").strip().lower()
    return s in ["", "pending", "queued"]


def main():
    q = load_queue()

    if q.empty:
        print("[manual_queue] queue empty")
        save_queue(q)
        return

    pending_mask = q["status"].apply(is_pending_status)
    pending_indices = list(q[pending_mask].index)

    if not pending_indices:
        print("[manual_queue] no pending items")
        save_queue(q)
        return

    pending_indices = pending_indices[:MAX_QUEUE_ITEMS]

    print(f"[manual_queue] pending_total={pending_mask.sum()}, processing={len(pending_indices)}")

    db = load_db()
    hist = load_history()

    print(f"[manual_queue] db_rows_before={len(db)}")
    print(f"[manual_queue] history_rows_before={len(hist)}")

    processed_count = 0
    failed_count = 0

    for idx in pending_indices:
        url = str(q.at[idx, "url"] or "").strip()

        if not url:
            q.at[idx, "status"] = "failed"
            q.at[idx, "processed_at"] = pd.Timestamp.now(tz="UTC").isoformat()
            q.at[idx, "error"] = "empty url"
            failed_count += 1
            continue

        print(f"[manual_queue] processing idx={idx} url={url}")

        try:
            song_id = resolve_suno_song_id(url)
            print(f"[manual_queue] resolved_song_id={song_id}")

            old_row = None

            if not db.empty and "id" in db.columns:
                db["id"] = db["id"].astype(str)
                matched = db[db["id"] == str(song_id)]

                if not matched.empty:
                    old_row = matched.iloc[0]

            clip, err = fetch_song_public(song_id)

            if not clip:
                raise RuntimeError(f"failed to fetch song: {err}")

            new_row = flatten_song(
                clip,
                old_row=old_row,
                source="manual_queue",
            )

            validate_created_at(new_row)

            db = upsert_song(db, new_row)
            hist = append_history(hist, new_row)

            q.at[idx, "status"] = "processed"
            q.at[idx, "song_id"] = str(song_id)
            q.at[idx, "title"] = str(new_row.get("title", ""))
            q.at[idx, "processed_at"] = pd.Timestamp.now(tz="UTC").isoformat()
            q.at[idx, "error"] = ""

            processed_count += 1

            print(
                f"[manual_queue OK] id={song_id} "
                f"title={new_row.get('title')} "
                f"play={new_row.get('play_count')} "
                f"like={new_row.get('upvote_count')} "
                f"comment={new_row.get('comment_count')}"
            )

        except Exception as e:
            q.at[idx, "status"] = "failed"
            q.at[idx, "processed_at"] = pd.Timestamp.now(tz="UTC").isoformat()
            q.at[idx, "error"] = str(e)[:500]

            failed_count += 1

            print(f"[manual_queue FAIL] url={url} error={e}")

        time.sleep(REQUEST_SLEEP_SECONDS)

    db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")
    hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")
    save_queue(q)

    check_db = pd.read_csv(DB_PATH)
    check_hist = pd.read_csv(HISTORY_PATH)
    check_queue = pd.read_csv(QUEUE_PATH)

    print(f"[manual_queue] db_rows_after={len(check_db)}")
    print(f"[manual_queue] history_rows_after={len(check_hist)}")
    print(f"[manual_queue] queue_rows={len(check_queue)}")
    print(f"[manual_queue done] processed={processed_count}, failed={failed_count}")


if __name__ == "__main__":
    main()
