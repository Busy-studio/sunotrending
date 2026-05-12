"""Manual Suno song queue helpers."""

import base64
import os
import time
import uuid
from io import StringIO

import pandas as pd
import requests
import streamlit as st

GITHUB_REPO_OWNER = st.secrets.get("GITHUB_REPO_OWNER", os.getenv("GITHUB_REPO_OWNER", "Busy-studio"))
GITHUB_REPO_NAME = st.secrets.get("GITHUB_REPO_NAME", os.getenv("GITHUB_REPO_NAME", "sunotrending"))
GITHUB_ACTION_TOKEN = st.secrets.get("GITHUB_ACTION_TOKEN", os.getenv("GITHUB_ACTION_TOKEN", ""))
MANUAL_QUEUE_BRANCH = st.secrets.get("MANUAL_QUEUE_BRANCH", os.getenv("MANUAL_QUEUE_BRANCH", "data"))
MANUAL_QUEUE_PATH = st.secrets.get("MANUAL_QUEUE_PATH", os.getenv("MANUAL_QUEUE_PATH", "data/manual_song_queue.csv"))

def is_valid_suno_link(url):
    url = str(url or "").strip()

    if not url:
        return False, "Suno 링크를 입력하세요."

    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.strip()

        if parsed.scheme not in ["http", "https"]:
            return False, "http 또는 https 링크만 사용할 수 있습니다."

        if host not in ["suno.com", "www.suno.com"]:
            return False, "suno.com 링크만 사용할 수 있습니다."

        if path.startswith("/song/"):
            return True, ""

        if path.startswith("/s/"):
            return True, ""

        return False, "지원하는 링크 형식은 /song/... 또는 /s/... 입니다."
    except Exception as e:
        return False, f"링크 확인 중 오류: {e}"


def queue_manual_song_url(song_url):
    if not GITHUB_ACTION_TOKEN:
        return False, "GITHUB_ACTION_TOKEN이 Streamlit secrets에 없습니다."

    clean_url = str(song_url or "").strip()

    if not clean_url:
        return False, "Suno 링크를 입력하세요."

    api_url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"
        f"/contents/{MANUAL_QUEUE_PATH}"
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_ACTION_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    columns = [
        "request_id",
        "submitted_at",
        "url",
        "status",
        "song_id",
        "title",
        "processed_at",
        "error",
    ]

    for attempt in range(3):
        try:
            sha = None

            get_response = requests.get(
                api_url,
                headers=headers,
                params={"ref": MANUAL_QUEUE_BRANCH},
                timeout=20,
            )

            if get_response.status_code == 200:
                payload = get_response.json()
                sha = payload.get("sha")
                encoded = payload.get("content", "")
                decoded = base64.b64decode(encoded).decode("utf-8-sig")

                if decoded.strip():
                    queue_df = pd.read_csv(
                        StringIO(decoded),
                        dtype=str,
                        keep_default_na=False,
                    )
                else:
                    queue_df = pd.DataFrame(columns=columns)

            elif get_response.status_code == 404:
                queue_df = pd.DataFrame(columns=columns)
            elif get_response.status_code == 403:
                return False, "GitHub queue 파일 접근 권한이 없습니다. 토큰에 Contents: Read and write 권한이 필요합니다."
            else:
                return False, f"GitHub queue 읽기 실패: {get_response.status_code} / {get_response.text[:300]}"

            for col in columns:
                if col not in queue_df.columns:
                    queue_df[col] = ""

            for col in columns:
                queue_df[col] = queue_df[col].fillna("").astype(str)

            duplicated_pending = queue_df[
                (queue_df["url"].str.strip() == clean_url)
                & (queue_df["status"].str.lower().isin(["pending", "queued", ""]))
            ]

            if not duplicated_pending.empty:
                return True, "이미 수집 대기열에 있는 링크입니다. 다음 업데이트 때 반영됩니다."

            new_row = {
                "request_id": str(uuid.uuid4()),
                "submitted_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "url": clean_url,
                "status": "pending",
                "song_id": "",
                "title": "",
                "processed_at": "",
                "error": "",
            }

            queue_df = pd.concat(
                [queue_df, pd.DataFrame([new_row])],
                ignore_index=True,
            )

            csv_text = queue_df[columns].to_csv(index=False, encoding="utf-8-sig")
            content_b64 = base64.b64encode(csv_text.encode("utf-8-sig")).decode("utf-8")

            put_payload = {
                "message": "Queue manual Suno song",
                "content": content_b64,
                "branch": MANUAL_QUEUE_BRANCH,
            }

            if sha:
                put_payload["sha"] = sha

            put_response = requests.put(
                api_url,
                headers=headers,
                json=put_payload,
                timeout=20,
            )

            if put_response.status_code in [200, 201]:
                return True, "곡 수집 대기열에 추가했습니다. 다음 업데이트 때 자동 반영됩니다."

            if put_response.status_code == 409:
                time.sleep(0.7)
                continue

            if put_response.status_code == 403:
                return False, "GitHub queue 저장 권한이 없습니다. 토큰에 Contents: Read and write 권한이 필요합니다."

            return False, f"GitHub queue 저장 실패: {put_response.status_code} / {put_response.text[:300]}"

        except Exception as e:
            if attempt >= 2:
                return False, f"queue 저장 중 오류: {e}"
            time.sleep(0.7)

    return False, "동시에 여러 요청이 들어와 queue 저장이 충돌했습니다. 잠시 후 다시 시도하세요."

