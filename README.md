# Suno Song Tracker Secure

This project tracks Suno song stats using public song pages and stores CSV data as AES-encrypted ZIP files.

## What it does

- Keeps `data/suno_song_db.csv` and `data/suno_song_history.csv` encrypted as ZIP files in GitHub.
- GitHub Actions decrypts the ZIP files with `DATA_ZIP_PASSWORD`, updates song stats, then encrypts them again.
- Streamlit decrypts the ZIP files with `st.secrets["DATA_ZIP_PASSWORD"]` and displays the dashboard.

## Required secrets

### GitHub Actions secret

Repository → Settings → Secrets and variables → Actions → New repository secret

Name:

```text
DATA_ZIP_PASSWORD
```

Value: your strong password.

### Streamlit secret

In Streamlit Cloud, set:

```toml
DATA_ZIP_PASSWORD = "your strong password"
```

For local testing, create `.streamlit/secrets.toml` from `.streamlit/secrets.toml.example`.

## First setup

1. Put your existing `suno_song_db.csv` into `data/suno_song_db.csv` locally.
2. Optionally put `suno_song_history.csv` into `data/suno_song_history.csv`.
3. Run:

```bash
export DATA_ZIP_PASSWORD="your strong password"
python scripts/encrypt_data.py
rm -f data/suno_song_db.csv data/suno_song_history.csv
```

4. Commit only:

```text
data/suno_song_db.zip
data/suno_song_history.zip
```

The `.gitignore` blocks plain CSV files from being committed.

## Run Streamlit locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run updater manually

```bash
export DATA_ZIP_PASSWORD="your strong password"
python scripts/decrypt_data.py
python scripts/update_public_song_pages.py
python scripts/encrypt_data.py
rm -f data/suno_song_db.csv data/suno_song_history.csv
```

## Notes

- This updater does not use Suno login tokens.
- It updates existing song IDs by reading public `https://suno.com/song/{id}` RSC page data.
- New song discovery still requires a separate source of song IDs. Add IDs to `data/suno_song_db.csv` before encryption, or extend the project later with a public discovery method.
