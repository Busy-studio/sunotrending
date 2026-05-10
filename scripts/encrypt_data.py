import os
import pandas as pd
from secure_csv import encrypt_file_to_zip

DATA_DIR = "data"
DB_CSV = os.path.join(DATA_DIR, "suno_song_db.csv")
HISTORY_CSV = os.path.join(DATA_DIR, "suno_song_history.csv")
DB_ZIP = os.path.join(DATA_DIR, "suno_song_db.zip")
HISTORY_ZIP = os.path.join(DATA_DIR, "suno_song_history.zip")


def ensure_default_csvs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(DB_CSV):
        pd.DataFrame(columns=[
            "id", "title", "handle", "display_name", "user_id", "created_at",
            "first_seen_at", "last_checked_at", "play_count", "upvote_count",
            "comment_count", "flag_count", "is_contest_clip", "contest_ids",
            "download_disabled_reason", "is_public", "is_hidden", "is_trashed",
            "explicit", "model", "major_model_version", "display_tags", "duration",
            "song_url", "audio_url", "image_url", "source",
        ]).to_csv(DB_CSV, index=False, encoding="utf-8-sig")

    if not os.path.exists(HISTORY_CSV):
        pd.DataFrame(columns=[
            "checked_at", "id", "title", "handle", "created_at",
            "play_count", "upvote_count", "comment_count", "flag_count",
        ]).to_csv(HISTORY_CSV, index=False, encoding="utf-8-sig")


def main() -> None:
    password = os.getenv("DATA_ZIP_PASSWORD")
    if not password:
        raise RuntimeError("DATA_ZIP_PASSWORD is missing")

    ensure_default_csvs()

    encrypt_file_to_zip(DB_CSV, DB_ZIP, password)
    encrypt_file_to_zip(HISTORY_CSV, HISTORY_ZIP, password)

    print(f"Encrypted {DB_CSV} -> {DB_ZIP}")
    print(f"Encrypted {HISTORY_CSV} -> {HISTORY_ZIP}")


if __name__ == "__main__":
    main()
