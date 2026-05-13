import os
import time
import argparse
import pandas as pd

from update_public_song_pages import (
    DB_PATH,
    ensure_data_files,
    choose_rows_to_update,
    restore_created_at_from_history,
    fetch_song_public,
    flatten_song,
    history_snapshot,
    is_blank_value,
    REQUEST_SLEEP_SECONDS,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch one shard of existing Suno song detail updates.")
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--output-dir", default="data/partial_updates")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.shard_count <= 0:
        raise ValueError("--shard-count must be positive")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise ValueError("--shard-index must be between 0 and shard-count - 1")

    ensure_data_files()
    os.makedirs(args.output_dir, exist_ok=True)

    db = pd.read_csv(DB_PATH)
    if not db.empty and "id" in db.columns:
        db["id"] = db["id"].astype(str)

    print(f"[shard {args.shard_index}] load db_rows={len(db)}")

    # Restore created_at before selecting stale rows, same as the full updater.
    db = restore_created_at_from_history(db)
    target = choose_rows_to_update(db)

    # Deterministic split: every shard sees the same ordered target list, then takes its slice.
    shard_target = target.iloc[args.shard_index::args.shard_count].copy()
    print(
        f"[shard {args.shard_index}] target_total={len(target)}, "
        f"shard_rows={len(shard_target)}, shard_count={args.shard_count}"
    )

    updated_rows = []
    history_rows = []
    success = 0
    failed = 0

    for _, row in shard_target.iterrows():
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
            success += 1
            print(
                f"[shard {args.shard_index} OK] {song_id} {new_row.get('title')} "
                f"play={new_row.get('play_count')} "
                f"like={new_row.get('upvote_count')} "
                f"comment={new_row.get('comment_count')} "
                f"lyrics={'yes' if not is_blank_value(new_row.get('lyrics')) else 'no'}"
            )
        else:
            failed += 1
            print(f"[shard {args.shard_index} FAIL] {song_id}: {err}")

        time.sleep(REQUEST_SLEEP_SECONDS)

    updates_path = os.path.join(args.output_dir, f"song_updates_shard_{args.shard_index}.csv")
    history_path = os.path.join(args.output_dir, f"song_history_shard_{args.shard_index}.csv")

    pd.DataFrame(updated_rows).to_csv(updates_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(history_rows).to_csv(history_path, index=False, encoding="utf-8-sig")

    print(
        f"[shard {args.shard_index} done] success={success}, failed={failed}, "
        f"updates={updates_path}, history={history_path}"
    )


if __name__ == "__main__":
    main()
