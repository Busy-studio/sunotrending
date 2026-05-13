import os
import pandas as pd

from update_public_song_pages import (
    DB_PATH,
    HISTORY_PATH,
    ensure_data_files,
    fetch_public_new_songs,
    add_new_songs_to_db,
    restore_created_at_from_history,
    prune_old_songs_and_history,
    serialize_datetime_columns_for_csv,
    normalize_text_columns,
    mojibake_report,
    detail_field_report,
)


def main():
    ensure_data_files()
    db = pd.read_csv(DB_PATH)
    if not db.empty and "id" in db.columns:
        db["id"] = db["id"].astype(str)

    print(f"[new_only] load db_rows={len(db)}")
    songs, logs = fetch_public_new_songs()
    for line in logs:
        print(line)

    db, added_count, duplicate_count = add_new_songs_to_db(db, songs)
    db = restore_created_at_from_history(db)

    print(
        f"[new_only] discovered={len(songs)}, added={added_count}, "
        f"duplicates={duplicate_count}, db_rows={len(db)}"
    )

    if "created_at" in db.columns:
        db["created_at_dt"] = pd.to_datetime(db["created_at"], errors="coerce", utc=True)
        db = db.sort_values("created_at_dt", ascending=False, na_position="last")
        db = db.drop(columns=["created_at_dt"], errors="ignore")

    db = prune_old_songs_and_history(db)

    text_changes = mojibake_report(db)
    if text_changes:
        print(f"[new_only] text_mojibake_fixed={text_changes}")
    db = normalize_text_columns(db)
    detail_field_report(db)

    db = serialize_datetime_columns_for_csv(db)
    db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")
    print(f"[new_only] saved db_rows={len(db)} -> {DB_PATH}")


if __name__ == "__main__":
    main()
