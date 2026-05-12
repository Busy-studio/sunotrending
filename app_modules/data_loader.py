"""Remote payload sync and encrypted data loading helpers for the Streamlit app."""

import os
import time
import json
import requests
import pandas as pd
import streamlit as st
from scripts.secure_csv import decrypt_zip_to_file

DB_ZIP_PATH = "data/suno_song_db.zip"
HISTORY_ZIP_PATH = "data/suno_song_history.zip"
APP_PAYLOAD_ZIP_PATH = "data/suno_app_payload.zip"
DATA_DIR = "data"

@st.cache_data(ttl=900)
def sync_remote_data_files(raw_base_url, github_token=""):
    if not raw_base_url:
        return {
            "enabled": False,
            "message": "DATA_RAW_BASE_URL is empty. Using local data files.",
        }

    os.makedirs(DATA_DIR, exist_ok=True)

    headers = {
        "Accept": "application/octet-stream",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "suno-trending-streamlit",
    }

    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    def download_one(filename, required=True):
        # GitHub Actions 주기와 맞춰 15분 단위 cache-bust.
        url = f"{raw_base_url}/{filename}?t={int(time.time() // 900)}"
        dest_path = os.path.join(DATA_DIR, filename)
        tmp_path = dest_path + ".tmp"

        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 404:
            if required:
                raise RuntimeError(f"Remote data file not found: {url}")
            return None

        response.raise_for_status()
        content = response.content

        if len(content) < 100:
            if required:
                raise RuntimeError(f"Remote data file looks too small: {filename}, {len(content)} bytes")
            return None

        with open(tmp_path, "wb") as f:
            f.write(content)

        os.replace(tmp_path, dest_path)
        return {"filename": filename, "bytes": len(content)}

    downloaded = []

    # 빠른 경로: 앱 표시용 payload 하나만 있으면 DB/history는 앱 시작 때 받지 않는다.
    payload_result = download_one("suno_app_payload.zip", required=False)
    if payload_result:
        downloaded.append(payload_result)
        return {
            "enabled": True,
            "message": "App payload synced.",
            "downloaded": downloaded,
        }

    # 첫 배포 직후 payload가 아직 없을 때만 기존 계산 fallback용 원본 데이터를 받는다.
    for filename in ["suno_song_db.zip", "suno_song_history.zip"]:
        result = download_one(filename, required=True)
        if result:
            downloaded.append(result)

    return {
        "enabled": True,
        "message": "Fallback DB/history files synced.",
        "downloaded": downloaded,
    }



def file_fingerprint(path):
    if not os.path.exists(path):
        return {
            "exists": False,
            "mtime_ns": 0,
            "size": 0,
        }

    stat = os.stat(path)

    return {
        "exists": True,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }

@st.cache_data(ttl=900)
def load_encrypted_data(db_fingerprint, history_fingerprint):
    password = st.secrets.get("DATA_ZIP_PASSWORD")

    if not password:
        return None, None, "DATA_ZIP_PASSWORD가 Streamlit secrets에 없습니다."

    db_csv_path = decrypt_zip_to_file(DB_ZIP_PATH, DATA_DIR, password)
    hist_csv_path = decrypt_zip_to_file(HISTORY_ZIP_PATH, DATA_DIR, password)

    if not db_csv_path or not os.path.exists(db_csv_path):
        return None, None, "Encrypted DB ZIP was not found or could not be extracted."

    db = pd.read_csv(db_csv_path)

    if hist_csv_path and os.path.exists(hist_csv_path):
        hist = pd.read_csv(hist_csv_path)
    else:
        hist = pd.DataFrame()

    return db, hist, ""


@st.cache_data(ttl=900)
def load_app_payload(payload_fingerprint):
    password = st.secrets.get("DATA_ZIP_PASSWORD")

    if not password:
        return None, "DATA_ZIP_PASSWORD가 Streamlit secrets에 없습니다."

    payload_path = decrypt_zip_to_file(APP_PAYLOAD_ZIP_PATH, DATA_DIR, password)

    if not payload_path or not os.path.exists(payload_path):
        return None, "suno_app_payload.zip이 아직 없습니다. 기존 DB 계산 모드로 전환합니다."

    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload, ""
    except Exception as e:
        return None, f"app payload를 읽지 못했습니다: {e}"


def payload_to_df(songs):
    if not songs:
        return pd.DataFrame()

    df = pd.DataFrame(songs)

    if "created_at_raw" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at_raw"], errors="coerce", utc=True)
    elif "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)

    return df


