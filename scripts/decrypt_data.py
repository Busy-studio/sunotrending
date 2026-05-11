import os
from secure_csv import decrypt_zip_to_file

DATA_DIR = "data"
DB_ZIP = os.path.join(DATA_DIR, "suno_song_db.zip")
HISTORY_ZIP = os.path.join(DATA_DIR, "suno_song_history.zip")
ARCHIVE_ZIP = os.path.join(DATA_DIR, "suno_song_archive.zip")


def main() -> None:
    password = os.getenv("DATA_ZIP_PASSWORD")
    if not password:
        raise RuntimeError("DATA_ZIP_PASSWORD is missing")

    db = decrypt_zip_to_file(DB_ZIP, DATA_DIR, password)
    hist = decrypt_zip_to_file(HISTORY_ZIP, DATA_DIR, password)
    archive = decrypt_zip_to_file(ARCHIVE_ZIP, DATA_DIR, password)

    print(f"Decrypted DB: {db}")
    print(f"Decrypted history: {hist}")
    if archive:
        print(f"Decrypted archive: {archive}")
    else:
        print(f"Archive zip not found yet: {ARCHIVE_ZIP}")


if __name__ == "__main__":
    main()
