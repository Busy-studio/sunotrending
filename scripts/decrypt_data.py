import os
from secure_csv import decrypt_zip_to_file

DATA_DIR = "data"
DB_ZIP = os.path.join(DATA_DIR, "suno_song_db.zip")
HISTORY_ZIP = os.path.join(DATA_DIR, "suno_song_history.zip")
ARCHIVE_ZIP = os.path.join(DATA_DIR, "suno_song_archive.zip")
APP_PAYLOAD_ZIP = os.path.join(DATA_DIR, "suno_app_payload.zip")
RANK_HISTORY_ZIP = os.path.join(DATA_DIR, "suno_rank_history.zip")


def main() -> None:
    password = os.getenv("DATA_ZIP_PASSWORD")
    if not password:
        raise RuntimeError("DATA_ZIP_PASSWORD is missing")

    db = decrypt_zip_to_file(DB_ZIP, DATA_DIR, password)
    hist = decrypt_zip_to_file(HISTORY_ZIP, DATA_DIR, password)
    archive = decrypt_zip_to_file(ARCHIVE_ZIP, DATA_DIR, password)
    payload = decrypt_zip_to_file(APP_PAYLOAD_ZIP, DATA_DIR, password)
    rank_history = decrypt_zip_to_file(RANK_HISTORY_ZIP, DATA_DIR, password)

    print(f"Decrypted DB: {db}")
    print(f"Decrypted history: {hist}")
    if archive:
        print(f"Decrypted archive: {archive}")
    else:
        print(f"Archive zip not found yet: {ARCHIVE_ZIP}")
    if payload:
        print(f"Decrypted app payload: {payload}")
    else:
        print(f"App payload zip not found yet: {APP_PAYLOAD_ZIP}")
    if rank_history:
        print(f"Decrypted rank history: {rank_history}")
    else:
        print(f"Rank history zip not found yet: {RANK_HISTORY_ZIP}")


if __name__ == "__main__":
    main()
