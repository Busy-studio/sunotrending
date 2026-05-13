import glob
import os
import pandas as pd

from update_public_song_pages import (
    DB_PATH,
    HISTORY_PATH,
    ensure_data_files,
    restore_created_at_from_history,
    prune_old_songs_and_history,
    serialize_datetime_columns_for_csv,
    normalize_text_columns,
    mojibake_report,
    detail_field_report,
)

PARTIAL_DIR = os.getenv("PARTIAL_UPDATE_DIR", "data/partial_updates")


def _read_non_empty_csv(path):
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except FileNotFoundError:
        return pd.DataFrame()
    return df


def main():
    ensure_data_files()

    db = pd.read_csv(DB_PATH)
    if not db.empty and "id" in db.columns:
        db["id"] = db["id"].astype(str)

    print(f"[merge_shards] load db_rows={len(db)}")

    update_files = sorted(glob.glob(os.path.join(PARTIAL_DIR, "song_updates_shard_*.csv")))
    history_files = sorted(glob.glob(os.path.join(PARTIAL_DIR, "song_history_shard_*.csv")))

    print(f"[merge_shards] update_files={len(update_files)} history_files={len(history_files)}")

    update_frames = []
    for path in update_files:
        df = _read_non_empty_csv(path)
        print(f"[merge_shards] {path} rows={len(df)}")
        if not df.empty:
            update_frames.append(df)

    history_frames = []
    for path in history_files:
        df = _read_non_empty_csv(path)
        print(f"[merge_shards] {path} rows={len(df)}")
        if not df.empty:
            history_frames.append(df)

    if update_frames:
        updates = pd.concat(update_frames, ignore_index=True)
        if "id" in updates.columns:
            updates["id"] = updates["id"].astype(str)
            updates = updates.drop_duplicates(subset=["id"], keep="last")

        updated_ids = set(updates["id"].dropna().astype(str)) if "id" in updates.columns else set()
        rest = db[~db["id"].isin(updated_ids)].copy() if "id" in db.columns else db.copy()
        final_db = pd.concat([updates, rest], ignore_index=True)
        print(f"[merge_shards] merged_updates={len(updates)} updated_ids={len(updated_ids)}")
    else:
        final_db = db.copy()
        print("[merge_shards] no shard updates found; keeping DB as-is")

    if "id" in final_db.columns:
        final_db["id"] = final_db["id"].astype(str)
        final_db = final_db.drop_duplicates(subset=["id"], keep="first")

    final_db = restore_created_at_from_history(final_db)

    if "created_at" in final_db.columns:
        final_db["created_at_dt"] = pd.to_datetime(final_db["created_at"], errors="coerce", utc=True)
        final_db = final_db.sort_values("created_at_dt", ascending=False, na_position="last")
        final_db = final_db.drop(columns=["created_at_dt"], errors="ignore")

    print(f"[merge_shards] before_prune db_rows={len(final_db)}")
    final_db = prune_old_songs_and_history(final_db)
    print(f"[merge_shards] after_prune db_rows={len(final_db)}")

    text_changes = mojibake_report(final_db)
    if text_changes:
        print(f"[merge_shards] text_mojibake_fixed={text_changes}")
    final_db = normalize_text_columns(final_db)
    detail_field_report(final_db)

    final_db = serialize_datetime_columns_for_csv(final_db)
    final_db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")
    print(f"[merge_shards] saved db_rows={len(final_db)} -> {DB_PATH}")

    if history_frames:
        hist_new = pd.concat(history_frames, ignore_index=True)
        if os.path.exists(HISTORY_PATH):
            hist_old = pd.read_csv(HISTORY_PATH)
            hist = pd.concat([hist_old, hist_new], ignore_index=True)
        else:
            hist = hist_new

        if "id" in hist.columns and "id" in final_db.columns:
            kept_ids = set(final_db["id"].dropna().astype(str))
            hist["id"] = hist["id"].astype(str)
            hist = hist[hist["id"].isin(kept_ids)].copy()

        hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")
        print(f"[merge_shards] saved history_rows={len(hist)} -> {HISTORY_PATH}")


if __name__ == "__main__":
    main()
