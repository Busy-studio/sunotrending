import os
import pandas as pd
from secure_csv import encrypt_file_to_zip

DATA_DIR = "data"
DB_CSV = os.path.join(DATA_DIR, "suno_song_db.csv")
HISTORY_CSV = os.path.join(DATA_DIR, "suno_song_history.csv")
ARCHIVE_CSV = os.path.join(DATA_DIR, "suno_song_archive.csv")
APP_PAYLOAD_JSON = os.path.join(DATA_DIR, "suno_app_payload.json")
RANK_HISTORY_CSV = os.path.join(DATA_DIR, "suno_rank_history.csv")
DB_ZIP = os.path.join(DATA_DIR, "suno_song_db.zip")
HISTORY_ZIP = os.path.join(DATA_DIR, "suno_song_history.zip")
ARCHIVE_ZIP = os.path.join(DATA_DIR, "suno_song_archive.zip")
APP_PAYLOAD_ZIP = os.path.join(DATA_DIR, "suno_app_payload.zip")
RANK_HISTORY_ZIP = os.path.join(DATA_DIR, "suno_rank_history.zip")


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
            "integrated_lufs", "true_peak_db", "loudness_gain_db",
            "loudness_target_lufs", "loudness_true_peak_ceiling_db",
            "loudness_checked_at", "loudness_status", "loudness_error",
            "loudness_audio_url_hash", "loudness_input_lra",
            "loudness_input_thresh", "loudness_target_offset",
        ]).to_csv(DB_CSV, index=False, encoding="utf-8-sig")

    if not os.path.exists(HISTORY_CSV):
        pd.DataFrame(columns=[
            "checked_at", "id", "title", "handle", "created_at",
            "play_count", "upvote_count", "comment_count", "flag_count",
        ]).to_csv(HISTORY_CSV, index=False, encoding="utf-8-sig")

    if not os.path.exists(ARCHIVE_CSV):
        pd.DataFrame(columns=[
            "archived_at", "archive_reason",
            "id", "title", "handle", "display_name", "user_id",
            "created_at", "first_seen_at", "last_checked_at",
            "play_count", "upvote_count", "comment_count", "adjusted_comment_count",
            "comment_quality_ratio", "meaningful_count", "generic_count",
            "mention_only_count", "emoji_only_count", "flag_count",
            "final_rank", "best_rank", "best_rank_at",
            "first_charted_at", "last_charted_at",
            "top10_count", "top50_count", "top200_count", "chart_in_count",
            "final_trend_score", "final_base_score", "final_growth_score", "final_freshness_score",
            "best_trend_score", "best_score_at",
            "peak_play_count", "peak_upvote_count", "peak_comment_count", "peak_adjusted_comment_count",
            "model", "major_model_version", "display_tags", "duration",
            "lyrics", "prompt", "gpt_description_prompt",
            "song_url", "audio_url", "image_url", "source",
            "integrated_lufs", "true_peak_db", "loudness_gain_db",
            "loudness_target_lufs", "loudness_true_peak_ceiling_db",
            "loudness_checked_at", "loudness_status", "loudness_error",
            "loudness_audio_url_hash", "loudness_input_lra",
            "loudness_input_thresh", "loudness_target_offset",
        ]).to_csv(ARCHIVE_CSV, index=False, encoding="utf-8-sig")

    if not os.path.exists(RANK_HISTORY_CSV):
        pd.DataFrame(columns=[
            "captured_at", "id", "rank",
            "trend_score", "base_score", "growth_score", "freshness_score",
            "play_count", "upvote_count", "comment_count", "adjusted_comment_count",
        ]).to_csv(RANK_HISTORY_CSV, index=False, encoding="utf-8-sig")


def main() -> None:
    password = os.getenv("DATA_ZIP_PASSWORD")
    if not password:
        raise RuntimeError("DATA_ZIP_PASSWORD is missing")

    ensure_default_csvs()

    encrypt_file_to_zip(DB_CSV, DB_ZIP, password)
    encrypt_file_to_zip(HISTORY_CSV, HISTORY_ZIP, password)
    encrypt_file_to_zip(ARCHIVE_CSV, ARCHIVE_ZIP, password)
    encrypt_file_to_zip(APP_PAYLOAD_JSON, APP_PAYLOAD_ZIP, password)
    encrypt_file_to_zip(RANK_HISTORY_CSV, RANK_HISTORY_ZIP, password)

    print(f"Encrypted {DB_CSV} -> {DB_ZIP}")
    print(f"Encrypted {HISTORY_CSV} -> {HISTORY_ZIP}")
    print(f"Encrypted {ARCHIVE_CSV} -> {ARCHIVE_ZIP}")
    if os.path.exists(APP_PAYLOAD_JSON):
        print(f"Encrypted {APP_PAYLOAD_JSON} -> {APP_PAYLOAD_ZIP}")
    if os.path.exists(RANK_HISTORY_CSV):
        print(f"Encrypted {RANK_HISTORY_CSV} -> {RANK_HISTORY_ZIP}")


if __name__ == "__main__":
    main()
