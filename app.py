import os
import math
import html
import json
import time
import requests
import base64
import uuid
from io import StringIO
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from scripts.secure_csv import decrypt_zip_to_file

try:
    import ftfy
except Exception:
    ftfy = None


DB_ZIP_PATH = "data/suno_song_db.zip"
HISTORY_ZIP_PATH = "data/suno_song_history.zip"
APP_PAYLOAD_ZIP_PATH = "data/suno_app_payload.zip"
DATA_DIR = "data"

# data branch에서 ZIP을 받아오기 위한 설정
# Streamlit secrets 또는 환경변수에 설정:
# DATA_RAW_BASE_URL = "https://raw.githubusercontent.com/OWNER/REPO/data/data"
DATA_RAW_BASE_URL = st.secrets.get(
    "DATA_RAW_BASE_URL",
    os.getenv("DATA_RAW_BASE_URL", "https://raw.githubusercontent.com/Busy-studio/sunotrending/data/data"),
).rstrip("/")

GITHUB_RAW_TOKEN = st.secrets.get(
    "GITHUB_RAW_TOKEN",
    os.getenv("GITHUB_RAW_TOKEN", ""),
)

GITHUB_REPO_OWNER = st.secrets.get(
    "GITHUB_REPO_OWNER",
    os.getenv("GITHUB_REPO_OWNER", "Busy-studio"),
)

GITHUB_REPO_NAME = st.secrets.get(
    "GITHUB_REPO_NAME",
    os.getenv("GITHUB_REPO_NAME", "sunotrending"),
)

GITHUB_WORKFLOW_FILE = st.secrets.get(
    "GITHUB_WORKFLOW_FILE",
    os.getenv("GITHUB_WORKFLOW_FILE", "update.yml"),
)

GITHUB_ACTION_TOKEN = st.secrets.get(
    "GITHUB_ACTION_TOKEN",
    os.getenv("GITHUB_ACTION_TOKEN", ""),
)

MANUAL_QUEUE_BRANCH = st.secrets.get(
    "MANUAL_QUEUE_BRANCH",
    os.getenv("MANUAL_QUEUE_BRANCH", "data"),
)

MANUAL_QUEUE_PATH = st.secrets.get(
    "MANUAL_QUEUE_PATH",
    os.getenv("MANUAL_QUEUE_PATH", "data/manual_song_queue.csv"),
)

RETENTION_HOURS = 96  # 4일
TOP_N = 200

# 고정 랭킹 설정
GROWTH_WINDOW_HOURS = 3
MAX_AGE_DAYS = 4
HIDE_CONTEST = False

PLAY_WEIGHT = 1.0
LIKE_WEIGHT = 3.0
COMMENT_WEIGHT = 4.0
GROWTH_WEIGHT = 1.5
FRESHNESS_WEIGHT = 35.0
FRESHNESS_POWER = 1.35

# 이상치 표시 설정
OUTLIER_SIGMA = 6.0
OUTLIER_USE_LOG = True


st.set_page_config(
    page_title="Suno Chart",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ================================
# Text helpers
# ================================

def broken_score(s: str) -> int:
    if not s:
        return 999999

    bad_markers = [
        "Ã", "ã", "Â", "â", "ð", "Ð", "Ñ", "Î", "Ï",
        "ç", "è", "é", "ê", "ë", "í", "ì", "Å", " ",
    ]

    score = sum(s.count(ch) * 3 for ch in bad_markers)
    score += sum(5 for ch in s if 0x80 <= ord(ch) <= 0x9F)
    score += max(0, 8 - len(s))

    return score


def try_decode_utf8_from_latinish(s: str):
    candidates = []

    for enc in ["latin1", "cp1252"]:
        try:
            fixed = s.encode(enc, errors="strict").decode("utf-8", errors="strict")
            if fixed:
                candidates.append(fixed)
        except Exception:
            pass

        try:
            fixed = s.encode(enc, errors="ignore").decode("utf-8", errors="ignore")
            if fixed:
                candidates.append(fixed)
        except Exception:
            pass

    return candidates


def fix_mojibake(value):
    if pd.isna(value):
        return ""

    original = str(value)

    if not original:
        return ""

    candidates = [original]

    if ftfy is not None:
        try:
            fixed = ftfy.fix_text(original)
            if fixed and fixed not in candidates:
                candidates.append(fixed)
        except Exception:
            pass

    frontier = list(candidates)

    for _ in range(3):
        new_frontier = []

        for s in frontier:
            for fixed in try_decode_utf8_from_latinish(s):
                if fixed and fixed not in candidates:
                    candidates.append(fixed)
                    new_frontier.append(fixed)

            if ftfy is not None:
                try:
                    fixed = ftfy.fix_text(s)
                    if fixed and fixed not in candidates:
                        candidates.append(fixed)
                        new_frontier.append(fixed)
                except Exception:
                    pass

        frontier = new_frontier

        if not frontier:
            break

    return min(candidates, key=broken_score)


def safe_text(value):
    if pd.isna(value):
        return ""

    s = fix_mojibake(value).strip()

    if s.lower() in ["nan", "none"]:
        return ""

    return s


def is_fake_rsc_token(value):
    s = safe_text(value)

    if not s:
        return True

    if s.startswith("$") and len(s) <= 8:
        return True

    return False


def safe_url(value):
    if pd.isna(value):
        return ""

    s = str(value).strip()

    if s.lower() in ["nan", "none", ""]:
        return ""

    return s

def safe_float_or_none(value):
    try:
        if pd.isna(value):
            return None

        s = str(value).strip()

        if s.lower() in ["", "nan", "none", "<na>", "null", "-"]:
            return None

        return float(s)
    except Exception:
        return None


def safe_int_or_none(value):
    try:
        f = safe_float_or_none(value)

        if f is None:
            return None

        return int(f)
    except Exception:
        return None


def normalize_handle(value):
    handle = safe_text(value)

    if not handle:
        return ""

    if handle.startswith("@"):
        handle = handle[1:]

    return handle


def build_creator_display(display_name_value, handle_value):
    display_name = safe_text(display_name_value)
    handle = normalize_handle(handle_value)

    primary = display_name or handle or "-"
    secondary = f"@{handle}" if handle else ""

    return primary, secondary


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

# ================================
# Data loading
# ================================

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


def clean_payload_text(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return fix_mojibake(value).strip()


def normalize_payload_song(song):
    if not isinstance(song, dict):
        return song

    # payload 경로에서는 CSV 전처리 단계를 건너뛰므로, 화면에 노출되는 텍스트를 한 번 더 복구한다.
    text_keys = [
        "title", "creator", "handle", "user_id", "created_at", "style_tags",
        "song_url", "audio_url", "image_url", "lyrics", "rank_status", "outlier_reasons",
    ]
    for key in text_keys:
        if key in song:
            song[key] = clean_payload_text(song.get(key))

    return song


def normalize_payload_songs(songs):
    return [normalize_payload_song(dict(song)) for song in (songs or []) if isinstance(song, dict)]




TAB_LABELS = {
    "new_songs": "New Song",
    "top200": "Top 200",
    "rain_crew": "☔rain crew",
}

TAB_DESCRIPTIONS = {
    "new_songs": "생성일 기준 최신순",
    "top200": "최근 4일 이내 곡 중 trend_score 상위 200",
    "rain_crew": "☔rain crew 설정에 포함된 크리에이터 곡 최신순",
}

def display_tab_label(key, raw_title=None):
    title = clean_payload_text(raw_title or "")
    return title or TAB_LABELS.get(str(key), str(key).replace("_", " ").title())

def display_tab_description(key, raw_description=None):
    description = clean_payload_text(raw_description or "")
    return description or TAB_DESCRIPTIONS.get(str(key), "")


def ranking_config_json():
    ranking_config = {
        "play_weight": PLAY_WEIGHT,
        "like_weight": LIKE_WEIGHT,
        "comment_weight": COMMENT_WEIGHT,
        "growth_weight": GROWTH_WEIGHT,
        "freshness_weight": FRESHNESS_WEIGHT,
        "freshness_power": FRESHNESS_POWER,
        "growth_window_hours": GROWTH_WINDOW_HOURS,
    }
    return json.dumps(ranking_config, ensure_ascii=False)


def render_player_ranking_payload(songs, histories=None, title="Top 200 Trending", subtitle=None):
    songs = normalize_payload_songs(songs)
    histories = histories or {}

    songs_json = json.dumps(songs, ensure_ascii=False).replace("</", "<\\/")
    histories_json = json.dumps(histories, ensure_ascii=False).replace("</", "<\\/")

    return render_player_ranking_html(
        songs_json,
        histories_json,
        ranking_config_json(),
        title=title,
        subtitle=subtitle,
    )


def render_player_ranking_payload_tabs(tabs_payload, tabs_order=None, default_key="top200"):
    tabs_payload = tabs_payload or {}
    tabs_order = tabs_order or list(tabs_payload.keys())

    cleaned_tabs = {}
    for key in tabs_order:
        tab = tabs_payload.get(key, {}) or {}
        songs = normalize_payload_songs(tab.get("songs", []) or [])
        histories = tab.get("histories", {}) or {}
        title = display_tab_label(key, tab.get("title"))
        description = display_tab_description(key, tab.get("description"))
        cleaned_tabs[key] = {
            "title": title,
            "description": description,
            "songs": songs,
            "histories": histories,
        }

    tabs_order = [key for key in tabs_order if key in cleaned_tabs]

    if not cleaned_tabs:
        st.info("표시할 탭 데이터가 없습니다.")
        return

    if default_key not in cleaned_tabs:
        default_key = tabs_order[0] if tabs_order else next(iter(cleaned_tabs.keys()))

    first_tab = cleaned_tabs.get(default_key, {})
    first_songs = first_tab.get("songs", []) or []
    first_histories = first_tab.get("histories", {}) or {}

    songs_json = json.dumps(first_songs, ensure_ascii=False).replace("</", "<\\/")
    histories_json = json.dumps(first_histories, ensure_ascii=False).replace("</", "<\\/")
    tabs_json = json.dumps(cleaned_tabs, ensure_ascii=False).replace("</", "<\\/")
    tabs_order_json = json.dumps(tabs_order, ensure_ascii=False).replace("</", "<\\/")

    return render_player_ranking_html(
        songs_json,
        histories_json,
        ranking_config_json(),
        title=first_tab.get("title") or "Suno Songs",
        subtitle=first_tab.get("description") or "앨범 이미지를 누르면 해당 곡을 재생 또는 일시정지합니다.",
        tabs_json=tabs_json,
        tabs_order_json=tabs_order_json,
        default_tab_key=default_key,
    )


def prepare_db(db):
    db = db.copy()

    text_cols = [
        "title",
        "handle",
        "display_name",
        "model",
        "display_tags",
        "lyrics",
        "prompt",
        "gpt_description_prompt",
        "rank_status",
        "comment_quality_summary",
    ]

    for col in text_cols:
        if col in db.columns:
            db[col] = db[col].apply(fix_mojibake)

    for col in ["created_at", "first_seen_at", "last_checked_at", "comment_quality_checked_at"]:
        if col in db.columns:
            db[col] = pd.to_datetime(db[col], errors="coerce", utc=True)

    numeric_cols = [
        "play_count",
        "upvote_count",
        "comment_count",
        "flag_count",
        "adjusted_comment_count",
        "comment_quality_ratio",
        "analyzed_comment_count",
        "meaningful_count",
        "generic_count",
        "mention_only_count",
        "emoji_only_count",
        "previous_rank",
        "current_rank",
        "rank_change",
    ]

    for col in numeric_cols:
        if col in db.columns:
            db[col] = pd.to_numeric(db[col], errors="coerce")
        else:
            db[col] = pd.NA

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        db[col] = db[col].fillna(0)

    if "adjusted_comment_count" in db.columns:
        db["adjusted_comment_count"] = db["adjusted_comment_count"].fillna(db["comment_count"])

    if "comment_quality_ratio" in db.columns:
        db["comment_quality_ratio"] = db["comment_quality_ratio"].fillna(1)

    if "id" in db.columns:
        db["id"] = db["id"].astype(str)

    if "song_url" not in db.columns and "id" in db.columns:
        db["song_url"] = "https://suno.com/song/" + db["id"].astype(str)

    return db


def prepare_history(hist):
    if hist is None or hist.empty:
        return pd.DataFrame()

    hist = hist.copy()

    for col in ["title", "handle"]:
        if col in hist.columns:
            hist[col] = hist[col].apply(fix_mojibake)

    if "checked_at" in hist.columns:
        hist["checked_at"] = pd.to_datetime(hist["checked_at"], errors="coerce", utc=True)

    if "created_at" in hist.columns:
        hist["created_at"] = pd.to_datetime(hist["created_at"], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col in hist.columns:
            hist[col] = pd.to_numeric(hist[col], errors="coerce").fillna(0)

    if "id" in hist.columns:
        hist["id"] = hist["id"].astype(str)

    return hist


# ================================
# Ranking
# ================================

def add_growth_features(db, hist, window_hours):
    db = db.copy()

    for col in [
        "play_delta_window",
        "upvote_delta_window",
        "comment_delta_window",
        "play_velocity_per_hour",
        "upvote_velocity_per_hour",
        "comment_velocity_per_hour",
    ]:
        db[col] = 0.0

    if hist.empty or "id" not in hist.columns or "checked_at" not in hist.columns:
        return db

    if "id" not in db.columns:
        return db

    hist = hist.copy()
    hist["id"] = hist["id"].astype(str)
    hist["checked_at"] = pd.to_datetime(hist["checked_at"], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count"]:
        if col in hist.columns:
            hist[col] = pd.to_numeric(hist[col], errors="coerce").fillna(0)
        else:
            hist[col] = 0

    db_created = db[["id", "created_at"]].copy()
    db_created["id"] = db_created["id"].astype(str)
    db_created = db_created.rename(columns={"created_at": "song_created_at"})
    db_created["song_created_at"] = pd.to_datetime(
        db_created["song_created_at"],
        errors="coerce",
        utc=True,
    )

    # hist 안에 created_at이 이미 있어도 충돌 안 나게 song_created_at이라는 별도 이름으로 붙임
    hist = hist.merge(db_created, on="id", how="left")

    agg_rows = []

    for song_id, g in hist.groupby("id"):
        g = g.sort_values("checked_at").copy()

        if g.empty:
            continue

        created_at = g["song_created_at"].dropna()

        if created_at.empty:
            continue

        created_at = created_at.iloc[0]

        # 생성 후 3시간이 지난 시점을 성장 기준점으로 잡음
        anchor_time = created_at + pd.Timedelta(hours=window_hours)

        # 생성 후 3시간 이후의 히스토리만 사용
        after_anchor = g[g["checked_at"] >= anchor_time].copy()

        if len(after_anchor) < 2:
            continue

        first = after_anchor.iloc[0]
        last = after_anchor.iloc[-1]

        hours = (last["checked_at"] - first["checked_at"]).total_seconds() / 3600

        if hours <= 0:
            continue

        play_delta_total = max(
            0,
            float(last.get("play_count", 0)) - float(first.get("play_count", 0))
        )
        upvote_delta_total = max(
            0,
            float(last.get("upvote_count", 0)) - float(first.get("upvote_count", 0))
        )
        comment_delta_total = max(
            0,
            float(last.get("comment_count", 0)) - float(first.get("comment_count", 0))
        )

        play_velocity = play_delta_total / hours
        upvote_velocity = upvote_delta_total / hours
        comment_velocity = comment_delta_total / hours

        # 기존 growth 공식은 "window_hours 동안의 증가량"을 기대하니까,
        # 기울기(per hour)를 다시 3시간 증가량 환산값으로 바꿔 넣음
        play_delta_window = play_velocity * window_hours
        upvote_delta_window = upvote_velocity * window_hours
        comment_delta_window = comment_velocity * window_hours

        agg_rows.append({
            "id": str(song_id),
            "play_delta_window": play_delta_window,
            "upvote_delta_window": upvote_delta_window,
            "comment_delta_window": comment_delta_window,
            "play_velocity_per_hour": play_velocity,
            "upvote_velocity_per_hour": upvote_velocity,
            "comment_velocity_per_hour": comment_velocity,
        })

    if not agg_rows:
        return db

    growth = pd.DataFrame(agg_rows)
    db = db.merge(growth, on="id", how="left", suffixes=("", "_growth"))

    for col in [
        "play_delta_window",
        "upvote_delta_window",
        "comment_delta_window",
        "play_velocity_per_hour",
        "upvote_velocity_per_hour",
        "comment_velocity_per_hour",
    ]:
        growth_col = f"{col}_growth"

        if growth_col in db.columns:
            db[col] = db[growth_col].fillna(db[col])
            db = db.drop(columns=[growth_col], errors="ignore")

        db[col] = db[col].fillna(0)

    return db


def score_songs(
    db,
    hist,
    play_weight,
    like_weight,
    comment_weight,
    growth_weight,
    freshness_weight,
    growth_window_hours,
    freshness_power,
):
    view = db.copy()

    now = pd.Timestamp.now(tz="UTC")

    if "created_at" not in view.columns:
        view["created_at"] = pd.NaT

    view["age_hours"] = (now - view["created_at"]).dt.total_seconds() / 3600
    view["age_hours"] = view["age_hours"].clip(lower=0)

    view["remaining_hours"] = (RETENTION_HOURS - view["age_hours"]).clip(lower=0)

    view["freshness"] = (view["remaining_hours"] / RETENTION_HOURS).clip(lower=0, upper=1)
    view["freshness_score"] = (view["freshness"] ** freshness_power) * freshness_weight

    view = add_growth_features(view, hist, growth_window_hours)

    for col in ["play_count", "upvote_count", "comment_count"]:
        if col not in view.columns:
            view[col] = 0
        view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0)

    if "adjusted_comment_count" in view.columns:
        view["effective_comment_count"] = pd.to_numeric(
            view["adjusted_comment_count"],
            errors="coerce",
        )
        view["effective_comment_count"] = view["effective_comment_count"].fillna(view["comment_count"])
    else:
        view["effective_comment_count"] = view["comment_count"]

    view["effective_comment_count"] = view["effective_comment_count"].clip(lower=0)

    view["base_score"] = (
        play_weight * view["play_count"].apply(lambda x: math.log1p(max(0, x)))
        + like_weight * view["upvote_count"].apply(lambda x: math.log1p(max(0, x)))
        + comment_weight * view["effective_comment_count"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score_raw"] = (
        0.4 * view["play_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 2.0 * view["upvote_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 3.0 * view["comment_delta_window"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score"] = view["growth_score_raw"] * growth_weight

    view["trend_score"] = (
        view["base_score"]
        + view["growth_score"]
        + view["freshness_score"]
    )

    return view


def add_outlier_flags(df, sigma=3.0, use_log=True):
    view = df.copy()

    metrics = {
        "play_count": "play",
        "upvote_count": "like",
        "comment_count": "comment",
    }

    view["is_outlier"] = False
    view["outlier_reasons"] = ""

    reason_lists = [[] for _ in range(len(view))]

    for col, label in metrics.items():
        if col not in view.columns:
            continue

        values = pd.to_numeric(view[col], errors="coerce").fillna(0)

        if use_log:
            values_for_z = values.apply(lambda x: math.log1p(max(0, x)))
        else:
            values_for_z = values

        mean = values_for_z.mean()
        std = values_for_z.std(ddof=0)

        if std == 0 or pd.isna(std):
            continue

        z = (values_for_z - mean) / std
        flag = z >= sigma

        view[f"{label}_zscore"] = z
        view[f"{label}_outlier"] = flag

        for i, is_flagged in enumerate(flag.tolist()):
            if is_flagged:
                raw_value = int(values.iloc[i])
                reason_lists[i].append(f"{label} {raw_value:,} / z={z.iloc[i]:.2f}")

    view["is_outlier"] = [len(x) > 0 for x in reason_lists]
    view["outlier_reasons"] = [" | ".join(x) for x in reason_lists]

    return view


def filter_view(df):
    view = df.copy()

    if HIDE_CONTEST:
        if "is_contest_clip" in view.columns:
            view = view[view["is_contest_clip"].astype(str).str.lower() != "true"]

        if "download_disabled_reason" in view.columns:
            view = view[view["download_disabled_reason"].astype(str) != "remix_contest"]

        if "contest_ids" in view.columns:
            contest_str = view["contest_ids"].astype(str).str.strip().str.lower()
            view = view[
                view["contest_ids"].isna()
                | (contest_str == "")
                | (contest_str == "nan")
                | (contest_str == "none")
            ]

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=MAX_AGE_DAYS)

    if "created_at" in view.columns:
        view = view[view["created_at"].isna() | (view["created_at"] >= cutoff)]

    return view


# ================================
# UI data
# ================================

def build_song_payload(df):
    songs = []

    for _, r in df.iterrows():
        display_name, handle_text = build_creator_display(
            r.get("display_name", ""),
            r.get("handle", ""),
        )

        created_at = r.get("created_at")

        if pd.notna(created_at):
            created_txt = created_at.strftime("%Y-%m-%d %H:%M UTC")
        else:
            created_txt = "-"

        lyrics_candidates = []

        for col in ["lyrics", "prompt", "gpt_description_prompt"]:
            if col in r.index:
                raw = r.get(col, "")

                if is_fake_rsc_token(raw):
                    continue

                txt = safe_text(raw)

                if txt:
                    lyrics_candidates.append(txt)

        lyrics_text = "\n\n".join(lyrics_candidates)

        raw_outlier = r.get("is_outlier", False)
        is_outlier = False if pd.isna(raw_outlier) else bool(raw_outlier)

        songs.append({
            "rank": int(safe_float_or_none(r.get("rank", 0)) or 0),
            "rank_change": safe_float_or_none(r.get("rank_change", None)),
            "rank_status": safe_text(r.get("rank_status", "")),
            "previous_rank": safe_int_or_none(r.get("previous_rank", None)),
            "current_rank_saved": safe_int_or_none(r.get("current_rank", None)),

            "id": safe_text(r.get("id", "")),
            "title": safe_text(r.get("title", "Untitled")) or "Untitled",
            "creator": display_name,
            "handle": handle_text,
            "created_at": created_txt,
            "style_tags": safe_text(r.get("display_tags", "")),

            "play_count": int(safe_float_or_none(r.get("play_count", 0)) or 0),
            "upvote_count": int(safe_float_or_none(r.get("upvote_count", 0)) or 0),
            "comment_count": int(safe_float_or_none(r.get("comment_count", 0)) or 0),
            "effective_comment_count": safe_float_or_none(r.get("effective_comment_count", r.get("comment_count", 0))) or 0,
            "adjusted_comment_count": safe_float_or_none(r.get("adjusted_comment_count", r.get("comment_count", 0))) or 0,
            "comment_quality_ratio": safe_float_or_none(r.get("comment_quality_ratio", 1)) or 1,

            "is_outlier": is_outlier,
            "outlier_reasons": safe_text(r.get("outlier_reasons", "")),

            "song_url": safe_url(r.get("song_url", "")),
            "audio_url": safe_url(r.get("audio_url", "")),
            "image_url": safe_url(r.get("image_url", "")),
            "lyrics": lyrics_text,

            "trend_score": safe_float_or_none(r.get("trend_score", 0)) or 0,
            "base_score": safe_float_or_none(r.get("base_score", 0)) or 0,
            "growth_score": safe_float_or_none(r.get("growth_score", 0)) or 0,
            "freshness_score": safe_float_or_none(r.get("freshness_score", 0)) or 0,
            "growth_score_raw": safe_float_or_none(r.get("growth_score_raw", 0)) or 0,
            "play_delta_window": safe_float_or_none(r.get("play_delta_window", 0)) or 0,
            "upvote_delta_window": safe_float_or_none(r.get("upvote_delta_window", 0)) or 0,
            "comment_delta_window": safe_float_or_none(r.get("comment_delta_window", 0)) or 0,
            "freshness": safe_float_or_none(r.get("freshness", 0)) or 0,
            "age_hours": safe_float_or_none(r.get("age_hours", 0)) or 0,
        })

    return songs


def build_history_payload(hist, song_ids):
    if hist is None or hist.empty:
        return {}

    if "id" not in hist.columns or "checked_at" not in hist.columns:
        return {}

    h = hist.copy()
    h["id"] = h["id"].astype(str)

    song_id_set = set(str(x) for x in song_ids)
    h = h[h["id"].isin(song_id_set)].copy()

    if h.empty:
        return {}

    h = h.sort_values("checked_at")

    result = {}

    for song_id, g in h.groupby("id"):
        rows = []
        g = g.tail(80)

        for _, r in g.iterrows():
            checked_at = r.get("checked_at")

            if pd.notna(checked_at):
                checked_txt = checked_at.strftime("%m-%d %H:%M")
            else:
                checked_txt = "-"

            rows.append({
                "checked_at": checked_txt,
                "play_count": int(float(r.get("play_count", 0) or 0)),
                "upvote_count": int(float(r.get("upvote_count", 0) or 0)),
                "comment_count": int(float(r.get("comment_count", 0) or 0)),
            })

        result[str(song_id)] = rows

    return result


# ================================
# Player + ranking component
# ================================

def render_player_ranking(df, hist):
    songs = build_song_payload(df)
    histories = build_history_payload(hist, [s["id"] for s in songs])

    songs_json = json.dumps(songs, ensure_ascii=False).replace("</", "<\\/")
    histories_json = json.dumps(histories, ensure_ascii=False).replace("</", "<\\/")

    return render_player_ranking_html(
        songs_json,
        histories_json,
        ranking_config_json(),
        title="Top 200",
        subtitle="최근 4일 이내 곡 중 trend_score 상위 200",
    )


def render_player_ranking_html(
    songs_json,
    histories_json,
    ranking_config_json,
    title="Top 200",
    subtitle=None,
    tabs_json="null",
    tabs_order_json="[]",
    default_tab_key="",
):
    title = clean_payload_text(title) or "Suno Songs"
    subtitle = clean_payload_text(subtitle) or "앨범 이미지를 누르면 해당 곡을 재생 또는 일시정지합니다."
    title_html = html.escape(title)
    subtitle_html = html.escape(subtitle)
    default_tab_key_js = json.dumps(default_tab_key or "", ensure_ascii=False)
    html_template = """
    <style>
    :root {
        --bg: #ffffff;
        --panel: #f8fafc;
        --line: #e5e7eb;
        --line-dark: #d1d5db;
        --text: #111827;
        --muted: #6b7280;
        --accent: #ef4444;
        --accent-dark: #dc2626;
        --soft: #f3f4f6;
    }

    * { box-sizing: border-box; }

    html, body {
        margin: 0;
        padding: 0;
        background: var(--bg);
        color: var(--text);
        font-family:
            "Noto Sans KR", "Noto Sans", "Apple SD Gothic Neo",
            "Malgun Gothic", "Segoe UI", Arial, sans-serif;
    }

    .app-shell {
        display: grid;
        grid-template-columns: 330px minmax(720px, 1fr);
        gap: 16px;
        width: 100%;
        min-height: 1200px;
    }

    .player-panel {
        position: sticky;
        top: 0;
        align-self: start;
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 14px;
        height: 1200px;
        overflow-y: auto;
    }

    .now-cover-wrap {
        width: 100%;
        aspect-ratio: 1 / 1;
        border-radius: 18px;
        overflow: hidden;
        background: #e5e7eb;
        margin-bottom: 12px;
        position: relative;
    }

    .now-cover {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }

    .now-placeholder {
        width: 100%;
        height: 100%;
        display: grid;
        place-items: center;
        color: var(--muted);
        font-size: 13px;
    }

    .now-title {
        font-size: 18px;
        font-weight: 850;
        line-height: 1.25;
        margin-bottom: 4px;
        word-break: break-word;
    }

    .now-creator {
        font-size: 13px;
        color: var(--muted);
        margin-bottom: 7px;
        word-break: break-word;
    }

    .now-style-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin: 0 0 10px 0;
        min-height: 20px;
    }

    .now-style-tag {
        display: inline-block;
        max-width: 125px;
        border: 1px solid var(--line);
        background: #ffffff;
        color: #374151;
        border-radius: 999px;
        padding: 3px 8px;
        font-size: 11px;
        line-height: 1.2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .now-style-empty {
        color: var(--muted);
        font-size: 12px;
    }

    .lyrics-panel {
        margin-top: 10px;
        border: 1px solid var(--line);
        background: #ffffff;
        border-radius: 12px;
        padding: 10px;
        height: 210px;
        overflow-y: auto;
        white-space: pre-wrap;
        font-size: 12px;
        line-height: 1.45;
        color: #374151;
    }

    .lyrics-panel.empty { color: var(--muted); }

    .progress-wrap { margin: 10px 0 8px 0; }

    .time-row {
        display: flex;
        justify-content: space-between;
        color: var(--muted);
        font-size: 11px;
        margin-top: 4px;
    }

    input[type="range"] {
        width: 100%;
        accent-color: var(--accent);
    }

    .control-row {
        display: flex;
        gap: 8px;
        align-items: center;
        justify-content: center;
        margin: 10px 0;
    }

    .ctrl-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 999px;
        min-width: 38px;
        height: 38px;
        cursor: pointer;
        font-weight: 800;
        font-size: 14px;
    }

    .ctrl-btn.main {
        background: var(--accent);
        color: white;
        border-color: var(--accent);
        min-width: 46px;
        height: 46px;
        font-size: 16px;
    }

    .ctrl-btn:hover { border-color: var(--accent); }

    .rank-change {
        text-align: center;
        white-space: nowrap;
        font-size: 12px;
        font-weight: 900;
        font-variant-numeric: tabular-nums;
    }

    .rank-up {
        color: #dc2626;
    }

    .rank-down {
        color: #2563eb;
    }

    .rank-new {
        color: #16a34a;
        font-weight: 950;
        letter-spacing: 0.02em;
    }

    .rank-same {
        color: var(--muted);
    }

    .mode-actions {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 6px;
        margin-bottom: 12px;
    }

    .small-btn {
        border: 1px solid var(--line-dark);
        background: white;
        color: var(--text);
        border-radius: 10px;
        padding: 8px 4px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 800;
        white-space: nowrap;
    }

    .small-btn.active {
        background: #fee2e2;
        color: var(--accent-dark);
        border-color: var(--accent);
    }

    .volume-row {
        display: grid;
        grid-template-columns: 54px 1fr 42px;
        gap: 8px;
        align-items: center;
        font-size: 12px;
        color: var(--muted);
        margin: 8px 0 12px 0;
    }

    .playlist-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 12px 0 8px 0;
    }

    .playlist-title {
        font-size: 14px;
        font-weight: 850;
    }

    .playlist-count {
        font-size: 12px;
        color: var(--muted);
    }

    .playlist {
        border: 1px solid var(--line);
        background: #ffffff;
        border-radius: 12px;
        overflow-y: auto;
        height: 260px;
    }

    .playlist-empty {
        color: var(--muted);
        font-size: 12px;
        padding: 14px;
        line-height: 1.5;
    }

    .playlist-item {
        display: grid;
        grid-template-columns: 34px 1fr 28px;
        gap: 8px;
        align-items: center;
        padding: 8px;
        border-bottom: 1px solid var(--line);
        cursor: pointer;
    }

    .playlist-item:last-child { border-bottom: 0; }
    .playlist-item.active { background: #fee2e2; }

    .playlist-thumb {
        width: 34px;
        height: 34px;
        border-radius: 8px;
        object-fit: cover;
        background: #e5e7eb;
    }

    .playlist-meta {
        overflow: hidden;
        min-width: 0;
    }

    .playlist-song-title {
        font-size: 12px;
        font-weight: 800;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .playlist-song-sub {
        font-size: 11px;
        color: var(--muted);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .remove-btn {
        border: 0;
        background: transparent;
        color: var(--muted);
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
    }

    .ranking-panel {
        min-width: 0;
        border: 1px solid var(--line);
        border-radius: 18px;
        overflow: hidden;
        background: #ffffff;
    }

    .ranking-topbar {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
        padding: 12px;
        background: #ffffff;
        border-bottom: 1px solid var(--line);
    }

    .rank-view-tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
        margin-bottom: 8px;
    }

    .rank-view-tab {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--muted);
        border-radius: 999px;
        padding: 7px 12px;
        font-size: 12px;
        font-weight: 900;
        cursor: pointer;
        transition: all 0.15s ease;
    }

    .rank-view-tab:hover {
        border-color: var(--accent);
        color: var(--accent);
    }

    .rank-view-tab.active {
        background: var(--accent);
        border-color: var(--accent);
        color: #ffffff;
    }

    .ranking-title {
        font-size: 16px;
        font-weight: 900;
    }

    .ranking-sub {
        color: var(--muted);
        font-size: 12px;
        margin-top: 2px;
    }

    .search-input {
        border: 1px solid var(--line-dark);
        border-radius: 999px;
        padding: 9px 13px;
        min-width: 260px;
        outline: none;
    }

    .search-input:focus { border-color: var(--accent); }

    .table-wrap {
        width: 100%;
        overflow-x: auto;
        max-height: 1120px;
        overflow-y: auto;
    }

    table.song-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        table-layout: fixed;
        color: var(--text);
    }

    .song-table th {
        text-align: left;
        padding: 11px 8px;
        border-bottom: 1px solid var(--line-dark);
        background: var(--soft);
        position: sticky;
        top: 0;
        z-index: 2;
        font-weight: 800;
        color: var(--text);
    }

    .song-table td {
        padding: 8px;
        border-bottom: 1px solid var(--line);
        vertical-align: middle;
        color: var(--text);
    }

    .song-table tr:hover { background: #f9fafb; }

    .song-table tr.outlier-row {
        background: #fff7ed;
    }

    .song-table tr.outlier-row:hover {
        background: #ffedd5;
    }

    .outlier-badge {
        display: inline-block;
        margin-left: 6px;
        border: 1px solid #f97316;
        background: #fed7aa;
        color: #9a3412;
        border-radius: 999px;
        padding: 2px 6px;
        font-size: 10px;
        font-weight: 900;
        vertical-align: middle;
        white-space: nowrap;
    }

    .select-cell { text-align: center; }

    .rank {
        font-weight: 850;
        font-size: 16px;
        text-align: right;
    }

    .cover-cell {
        display: flex;
        align-items: center;
    }

    .cover-btn {
        border: 0;
        padding: 0;
        margin: 0;
        background: transparent;
        cursor: pointer;
        position: relative;
        width: 56px;
        height: 56px;
        display: block;
        flex-shrink: 0;
    }

    .cover {
        width: 56px;
        height: 56px;
        object-fit: cover;
        border-radius: 10px;
        background: #e5e7eb;
        display: block;
    }

    .cover-btn::after {
        content: "▶";
        position: absolute;
        right: 4px;
        bottom: 4px;
        width: 20px;
        height: 20px;
        border-radius: 999px;
        background: rgba(0,0,0,0.72);
        color: white;
        font-size: 11px;
        line-height: 20px;
        text-align: center;
        font-weight: 800;
    }

    .cover-btn.playing::after {
        content: "Ⅱ";
        background: var(--accent);
    }

    .cover-btn.paused::after {
        content: "▶";
        background: var(--accent);
    }

    .add-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 8px;
        width: 32px;
        height: 32px;
        cursor: pointer;
        font-weight: 900;
    }

    .add-btn.added {
        color: white;
        background: var(--accent);
        border-color: var(--accent);
    }

    .title-cell {
        overflow: hidden;
        word-break: break-word;
        color: var(--text);
    }

    .title-link {
        font-weight: 850;
        text-decoration: none;
        color: var(--text);
        display: inline-block;
        max-width: 100%;
        white-space: normal;
        line-height: 1.35;
    }

    .title-link:hover {
        text-decoration: underline;
        color: var(--accent);
    }

    .style-cell {
        overflow: hidden;
        white-space: nowrap;
    }

    .style-tags {
        display: flex;
        flex-wrap: nowrap;
        gap: 4px;
        align-items: center;
        overflow: hidden;
        max-width: 100%;
    }

    .style-tag {
        display: inline-block;
        flex: 0 1 auto;
        min-width: 0;
        max-width: 84px;
        border: 1px solid var(--line);
        background: #f9fafb;
        color: #374151;
        border-radius: 999px;
        padding: 3px 7px;
        font-size: 11px;
        line-height: 1.2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .style-empty {
        color: var(--muted);
        font-size: 12px;
    }

    .subtle {
        color: var(--muted);
        font-size: 12px;
        margin-top: 4px;
        line-height: 1.25;
    }

    .creator {
        line-height: 1.35;
        word-break: break-word;
        color: var(--text);
    }

    .num {
        text-align: right;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
        color: var(--text);
    }

    .rank-info-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 999px;
        padding: 6px 10px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 800;
        white-space: nowrap;
    }

    .rank-info-btn:hover {
        border-color: var(--accent);
        color: var(--accent-dark);
    }

    .modal-backdrop {
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.45);
        z-index: 9999;
        padding: 28px;
        overflow-y: auto;
    }

    .modal-backdrop.open { display: block; }

    .modal-card {
        background: white;
        color: var(--text);
        border-radius: 18px;
        max-width: 780px;
        margin: 0 auto;
        padding: 18px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.25);
    }

    .modal-head {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: start;
        margin-bottom: 12px;
    }

    .modal-title {
        font-size: 18px;
        font-weight: 900;
        line-height: 1.3;
    }

    .modal-sub {
        color: var(--muted);
        font-size: 12px;
        margin-top: 4px;
    }

    .modal-close {
        border: 1px solid var(--line-dark);
        background: white;
        border-radius: 999px;
        cursor: pointer;
        width: 34px;
        height: 34px;
        font-weight: 900;
    }

    .score-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin: 12px 0;
    }

    .score-box {
        border: 1px solid var(--line);
        background: var(--panel);
        border-radius: 12px;
        padding: 10px;
    }

    .score-label {
        color: var(--muted);
        font-size: 11px;
        margin-bottom: 4px;
    }

    .score-value {
        font-size: 17px;
        font-weight: 900;
        font-variant-numeric: tabular-nums;
    }

    .song-table th.sortable {
        cursor: pointer;
        user-select: none;
    }

    .song-table th.sortable:hover {
        color: var(--accent-dark);
    }

    .sort-indicator {
        margin-left: 4px;
        font-size: 10px;
        color: var(--muted);
    }

    .chart-wrap {
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 10px;
        overflow-x: auto;
    }

    .footer-credit {
        margin-top: 16px;
        padding: 16px;
        text-align: center;
        color: var(--muted);
        font-size: 12px;
    }

    .footer-credit a {
        color: var(--accent-dark);
        font-weight: 900;
        text-decoration: none;
    }

    .footer-credit a:hover { text-decoration: underline; }

    @media (max-width: 980px) {
        .app-shell { grid-template-columns: 1fr; }

        .player-panel {
            position: relative;
            height: auto;
            max-height: none;
        }

        .playlist { height: 220px; }
        .lyrics-panel { height: 180px; }
        .score-grid { grid-template-columns: repeat(2, 1fr); }
    }
    </style>

    <div class="app-shell">
        <aside class="player-panel">
            <div class="now-cover-wrap" id="nowCoverWrap">
                <div class="now-placeholder">No track selected</div>
            </div>

            <div class="now-title" id="nowTitle">플레이리스트에 곡을 추가하세요</div>
            <div class="now-creator" id="nowCreator">앨범 이미지나 체크 버튼을 누르면 추가됩니다.</div>
            <div class="now-style-tags" id="nowStyleTags"></div>

            <div class="lyrics-panel empty" id="lyricsPanel">가사/프롬프트 정보가 있으면 여기에 표시됩니다.</div>

            <div class="progress-wrap">
                <input id="progress" type="range" min="0" max="1000" value="0">
                <div class="time-row">
                    <span id="currentTime">0:00</span>
                    <span id="duration">0:00</span>
                </div>
            </div>

            <div class="control-row">
                <button class="ctrl-btn" id="prevBtn" title="이전 곡">⏮</button>
                <button class="ctrl-btn main" id="playBtn" title="재생 / 일시정지">▶</button>
                <button class="ctrl-btn" id="nextBtn" title="다음 곡">⏭</button>
            </div>

            <div class="mode-actions">
                <button class="small-btn" id="repeatOneBtn">한곡 반복</button>
                <button class="small-btn active" id="repeatAllBtn">전체 반복</button>
                <button class="small-btn active" id="sequenceBtn">순차 재생</button>
                <button class="small-btn" id="shuffleBtn">랜덤 재생</button>
                <button class="small-btn" id="clearBtn">초기화</button>
            </div>

            <div class="volume-row">
                <span>Volume</span>
                <input id="volume" type="range" min="0" max="100" value="80">
                <span id="volumeText">80%</span>
            </div>

            <div class="playlist-head">
                <div class="playlist-title">Playlist</div>
                <div class="playlist-count" id="playlistCount">0 tracks</div>
            </div>

            <div class="playlist" id="playlist">
                <div class="playlist-empty">
                    아직 플레이리스트가 비어 있습니다.<br>
                    오른쪽 랭킹에서 앨범 이미지나 체크 버튼을 눌러 추가하세요.
                </div>
            </div>
        </aside>

        <main class="ranking-panel">
            <div class="ranking-topbar">
                <div>
                    <div class="rank-view-tabs" id="rankViewTabs"></div>
                    <div class="ranking-title" id="rankingTitle">{title_html}</div>
                    <div class="ranking-sub" id="rankingSub">{subtitle_html}</div>
                </div>
                <input class="search-input" id="searchInput" placeholder="Search title / style / creator / handle">
            </div>

            <div class="table-wrap">
                <table class="song-table">
                    <thead>
                        <tr>
                            <th style="width:46px; text-align:center;">선택</th>
                            <th class="sortable" data-sort-key="rank" style="width:42px; text-align:right;">순위<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="rank_change" style="width:58px; text-align:center;">변동<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="has_image" style="width:76px;">앨범<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="title" style="width:360px;">곡 제목<span class="sort-indicator"></span></th>
                            <th style="width:170px;">스타일</th>
                            <th class="sortable" data-sort-key="creator" style="width:210px;">창작자<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="play_count" style="width:76px; text-align:right;">플레이<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="upvote_count" style="width:76px; text-align:right;">좋아요<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="comment_count" style="width:64px; text-align:right;">댓글<span class="sort-indicator"></span></th>
                            <th style="width:90px; text-align:center;">상세정보</th>
                        </tr>
                    </thead>
                    <tbody id="songTableBody"></tbody>
                </table>
            </div>

            <div class="footer-credit">
                This page was created by
                <a href="https://suno.com/@busystudio" target="_blank" rel="noopener noreferrer">Busy Studio</a>.
            </div>
        </main>
    </div>

    <div class="modal-backdrop" id="rankingModal">
        <div class="modal-card">
            <div class="modal-head">
                <div>
                    <div class="modal-title" id="modalTitle">Detailed Info</div>
                    <div class="modal-sub" id="modalSub"></div>
                </div>
                <button class="modal-close" id="modalCloseBtn">×</button>
            </div>

            <div class="score-grid">
                <div class="score-box">
                    <div class="score-label">Trend Score</div>
                    <div class="score-value" id="scoreTrend">0</div>
                </div>
                <div class="score-box">
                    <div class="score-label">Base</div>
                    <div class="score-value" id="scoreBase">0</div>
                </div>
                <div class="score-box">
                    <div class="score-label">Growth</div>
                    <div class="score-value" id="scoreGrowth">0</div>
                </div>
                <div class="score-box">
                    <div class="score-label">Freshness</div>
                    <div class="score-value" id="scoreFreshness">0</div>
                </div>
            </div>

            <div class="chart-wrap">
                <canvas id="historyCanvas" width="720" height="260"></canvas>
            </div>
        </div>
    </div>

    <script>
    let songs = __SONGS_JSON__;
    let histories = __HISTORIES_JSON__;
    const rankingConfig = __RANKING_CONFIG_JSON__;
    const tabsData = __TABS_JSON__;
    const tabsOrder = __TABS_ORDER_JSON__;
    const defaultTabKey = __DEFAULT_TAB_KEY__;

    let playlist = [];
    let currentIndex = -1;
    let audio = new Audio();

    let repeatOne = false;
    let repeatAll = true;
    let playbackMode = "sequence";

    let sortState = {
        key: null,
        direction: null,
    };

    const nowCoverWrap = document.getElementById("nowCoverWrap");
    const nowTitle = document.getElementById("nowTitle");
    const nowCreator = document.getElementById("nowCreator");
    const nowStyleTags = document.getElementById("nowStyleTags");
    const playlistEl = document.getElementById("playlist");
    const playlistCount = document.getElementById("playlistCount");
    const lyricsPanel = document.getElementById("lyricsPanel");

    const playBtn = document.getElementById("playBtn");
    const prevBtn = document.getElementById("prevBtn");
    const nextBtn = document.getElementById("nextBtn");
    const repeatOneBtn = document.getElementById("repeatOneBtn");
    const repeatAllBtn = document.getElementById("repeatAllBtn");
    const sequenceBtn = document.getElementById("sequenceBtn");
    const shuffleBtn = document.getElementById("shuffleBtn");
    const clearBtn = document.getElementById("clearBtn");
    const volume = document.getElementById("volume");
    const volumeText = document.getElementById("volumeText");
    const progress = document.getElementById("progress");
    const currentTimeEl = document.getElementById("currentTime");
    const durationEl = document.getElementById("duration");
    const searchInput = document.getElementById("searchInput");
    const rankViewTabs = document.getElementById("rankViewTabs");
    const rankingTitle = document.getElementById("rankingTitle");
    const rankingSub = document.getElementById("rankingSub");
    const songTableBody = document.getElementById("songTableBody");

    const rankingModal = document.getElementById("rankingModal");
    const modalCloseBtn = document.getElementById("modalCloseBtn");
    const modalTitle = document.getElementById("modalTitle");
    const modalSub = document.getElementById("modalSub");
    const scoreTrend = document.getElementById("scoreTrend");
    const scoreBase = document.getElementById("scoreBase");
    const scoreGrowth = document.getElementById("scoreGrowth");
    const scoreFreshness = document.getElementById("scoreFreshness");
    const historyCanvas = document.getElementById("historyCanvas");

    function escapeHtml(text) {
        if (text === null || text === undefined) return "";

        return String(text)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    const TAB_LABEL_FALLBACKS = {
        "new_songs": "New Song",
        "top200": "Top 200",
        "rain_crew": "☔rain crew",
    };

    const TAB_DESCRIPTION_FALLBACKS = {
        "new_songs": "생성일 기준 최신순",
        "top200": "최근 4일 이내 곡 중 trend_score 상위 200",
        "rain_crew": "☔rain crew 설정에 포함된 크리에이터 곡 최신순",
    };

    function prettifyTabKey(key) {
        return String(key || "")
            .split("_")
            .filter(Boolean)
            .map(part => part.charAt(0).toUpperCase() + part.slice(1))
            .join(" ");
    }

    function getTabTitle(key, tab) {
        const raw = tab && tab.title ? String(tab.title).trim() : "";
        if (raw) return raw;
        return TAB_LABEL_FALLBACKS[key] || prettifyTabKey(key) || "Suno Songs";
    }

    function getTabDescription(key, tab) {
        const raw = tab && tab.description ? String(tab.description).trim() : "";
        if (raw) return raw;
        return TAB_DESCRIPTION_FALLBACKS[key] || "앨범 이미지를 누르면 해당 곡을 재생 또는 일시정지합니다.";
    }

    function formatInt(n) {
        try {
            return Number(n || 0).toLocaleString();
        } catch (e) {
            return "0";
        }
    }

    function formatFloat(n, digits = 2) {
        try {
            return Number(n || 0).toFixed(digits);
        } catch (e) {
            return "0.00";
        }
    }

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) return "0:00";

        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);

        return `${m}:${String(s).padStart(2, "0")}`;        
    }

function getSortableValue(song, key) {
    if (key === "rank") {
        return Number(song.rank || 0);
    }

    if (key === "rank_change") {
        if (song.rank_status === "new") return 999999;
        if (song.rank_change === null || song.rank_change === undefined || song.rank_change === "") return 0;
        return Number(song.rank_change || 0);
    }

    if (key === "has_image") {
        return song.image_url ? 1 : 0;
    }

    if (key === "title") {
        return String(song.title || "").toLowerCase();
    }

    if (key === "creator") {
        return String(song.creator || "").toLowerCase();
    }

    if (key === "style_tags") {
        return String(song.style_tags || "").toLowerCase();
    }

    if (key === "play_count") {
        return Number(song.play_count || 0);
    }

    if (key === "upvote_count") {
        return Number(song.upvote_count || 0);
    }

    if (key === "comment_count") {
        return Number(song.comment_count || 0);
    }

    return "";
}

function sortSongsForView(list) {
    if (!sortState.key || !sortState.direction) {
        return list.slice().sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
    }

    const key = sortState.key;
    const direction = sortState.direction;

    return list.slice().sort((a, b) => {
        const av = getSortableValue(a, key);
        const bv = getSortableValue(b, key);

        let result = 0;

        if (typeof av === "number" && typeof bv === "number") {
            result = av - bv;
        } else {
            result = String(av).localeCompare(String(bv), "ko", {
                numeric: true,
                sensitivity: "base",
            });
        }

        if (result === 0) {
            result = Number(a.rank || 0) - Number(b.rank || 0);
        }

        return direction === "asc" ? result : -result;
    });
}

function updateSortIndicators() {
    document.querySelectorAll("th.sortable").forEach(th => {
        const indicator = th.querySelector(".sort-indicator");
        if (!indicator) return;

        const key = th.dataset.sortKey;

        if (sortState.key !== key || !sortState.direction) {
            indicator.textContent = "";
            return;
        }

        indicator.textContent = sortState.direction === "asc" ? "▲" : "▼";
    });
}

function cycleSort(key) {
    if (sortState.key !== key) {
        sortState.key = key;
        sortState.direction = "asc";
    } else if (sortState.direction === "asc") {
        sortState.direction = "desc";
    } else if (sortState.direction === "desc") {
        sortState.key = null;
        sortState.direction = null;
    } else {
        sortState.direction = "asc";
    }

    renderTable(searchInput.value || "");
}

    function renderRankChange(value, status) {
        if (status === "new") {
            return `<span class="rank-new">NEW</span>`;
        }

        if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
            return `<span class="rank-same">-</span>`;
        }

        const n = Number(value);

        if (!isFinite(n) || n === 0) {
            return `<span class="rank-same">-</span>`;
        }

        const absN = Math.abs(Math.round(n));

        if (n > 0) {
            return `<span class="rank-up">▲${absN}</span>`;
        }

        return `<span class="rank-down">▽${absN}</span>`;
    }

    function parseStyleTags(value) {
        if (!value) return [];

        let text = String(value).trim();

        if (!text || text.toLowerCase() === "nan" || text.toLowerCase() === "none") {
            return [];
        }

        let tags = [];

        try {
            const parsed = JSON.parse(text);

            if (Array.isArray(parsed)) {
                tags = parsed.map(x => String(x).trim()).filter(Boolean);
            }
        } catch (e) {
            tags = [];
        }

        if (!tags.length) {
            tags = text
                .replaceAll("[", "")
                .replaceAll("]", "")
                .replaceAll('"', "")
                .replaceAll("'", "")
                .split(/[,|#]/)
                .map(x => x.trim())
                .filter(Boolean);
        }

        return tags;
    }

    function renderStyleTags(value) {
        const tags = parseStyleTags(value);

        if (!tags.length) {
            return `<span class="style-empty">-</span>`;
        }

        return `
            <div class="style-tags">
                ${tags.slice(0, 4).map(tag => `<span class="style-tag" title="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`).join("")}
            </div>
        `;
    }

    function renderNowStyleTags(value) {
        const tags = parseStyleTags(value);

        if (!tags.length) {
            return `<span class="now-style-empty">스타일 정보 없음</span>`;
        }

        return tags.slice(0, 8).map(tag => {
            return `<span class="now-style-tag" title="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`;
        }).join("");
    }

    function getCurrentSong() {
        if (currentIndex < 0 || currentIndex >= playlist.length) return null;
        return playlist[currentIndex];
    }

    function getSongById(id) {
        return songs.find(s => String(s.id) === String(id));
    }

    function isCurrentSong(song) {
        const current = getCurrentSong();
        return current && String(current.id) === String(song.id);
    }

    function updateVolume() {
        const v = Number(volume.value || 80) / 100;
        volumeText.textContent = `${Math.round(v * 100)}%`;
        audio.volume = v;
    }

    function renderTable(filterText = "") {
        const q = String(filterText || "").trim().toLowerCase();

        let filtered = songs.filter(song => {
            if (!q) return true;

            const hay = [
                song.title,
                song.style_tags,
                song.creator,
                song.handle,
                song.id
            ].join(" ").toLowerCase();

            return hay.includes(q);
        });

        filtered = sortSongsForView(filtered);

        if (!q) {
            filtered = filtered.slice(0, 200);
        }

        updateSortIndicators();

        if (!filtered.length) {
            songTableBody.innerHTML = `
                <tr>
                    <td colspan="11" style="padding:18px; text-align:center; color:#6b7280;">
                        표시할 곡이 없습니다.
                    </td>
                </tr>
            `;
            return;
        }

        songTableBody.innerHTML = filtered.map(song => {
            const imageHtml = song.image_url
                ? `<img class="cover" src="${escapeHtml(song.image_url)}" loading="lazy">`
                : `<div class="cover"></div>`;

            const titleHtml = song.song_url
                ? `<a class="title-link" href="${escapeHtml(song.song_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(song.title)}</a>`
                : `<span class="title-link">${escapeHtml(song.title)}</span>`;

            const handleHtml = song.handle
                ? `<div class="subtle">${escapeHtml(song.handle)}</div>`
                : "";

            const outlierClass = song.is_outlier ? "outlier-row" : "";
            const outlierBadge = song.is_outlier
                ? `<span class="outlier-badge" title="${escapeHtml(song.outlier_reasons)}">⚠</span>`
                : "";

            return `
                <tr class="${outlierClass}" data-song-id="${escapeHtml(song.id)}">
                    <td class="select-cell">
                        <button class="add-btn" data-action="toggle-playlist" data-song-id="${escapeHtml(song.id)}" title="선택 / 해제">+</button>
                    </td>
                    <td class="rank">${song.rank}</td>
                    <td class="rank-change">${renderRankChange(song.rank_change, song.rank_status)}</td>
                    <td>
                        <div class="cover-cell">
                            <button class="cover-btn" data-action="cover-click" data-song-id="${escapeHtml(song.id)}" title="재생 / 일시정지">
                                ${imageHtml}
                            </button>
                        </div>
                    </td>
                    <td class="title-cell">
                        ${titleHtml} ${outlierBadge}
                        <div class="subtle">${escapeHtml(song.created_at)}</div>
                    </td>
                    <td class="style-cell">
                        ${renderStyleTags(song.style_tags)}
                    </td>
                    <td class="creator">
                        ${escapeHtml(song.creator)}
                        ${handleHtml}
                    </td>
                    <td class="num">${formatInt(song.play_count)}</td>
                    <td class="num">${formatInt(song.upvote_count)}</td>
                    <td class="num">${formatInt(song.comment_count)}</td>
                    <td style="text-align:center;">
                        <button class="rank-info-btn" data-action="rank-info" data-song-id="${escapeHtml(song.id)}">상세정보</button>
                    </td>
                </tr>
            `;
        }).join("");

        bindTableEvents();
        refreshButtonsAndCovers();
    }

    function bindTableEvents() {
        songTableBody.querySelectorAll("[data-action='toggle-playlist']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                togglePlaylist(btn.dataset.songId);
            });
        });

        songTableBody.querySelectorAll("[data-action='cover-click']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                coverClick(btn.dataset.songId);
            });
        });

        songTableBody.querySelectorAll("[data-action='rank-info']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                openRankingInfo(btn.dataset.songId);
            });
        });
    }

    function bindSortHeaderEvents() {
        document.querySelectorAll("th.sortable").forEach(th => {
            th.addEventListener("click", event => {
                event.preventDefault();

                const key = th.dataset.sortKey;
                if (!key) return;

                cycleSort(key);
            });
        });
    }

    function bindPlaylistEvents() {
        playlistEl.querySelectorAll("[data-action='play-playlist-index']").forEach(item => {
            item.addEventListener("click", event => {
                event.preventDefault();
                playPlaylistIndex(Number(item.dataset.index));
            });
        });

        playlistEl.querySelectorAll("[data-action='remove-playlist']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                removeFromPlaylistById(btn.dataset.songId);
            });
        });
    }

    function addToPlaylist(id) {
        const song = getSongById(id);

        if (!song) return false;

        if (!song.audio_url) {
            alert("이 곡에는 audio_url이 없습니다.");
            return false;
        }

        if (!playlist.some(s => String(s.id) === String(song.id))) {
            playlist.push(song);
        }

        if (currentIndex === -1) {
            currentIndex = playlist.findIndex(s => String(s.id) === String(song.id));
            loadCurrent(false);
        }

        renderPlaylist();
        refreshButtonsAndCovers();

        return true;
    }

    function removeFromPlaylistById(id) {
        const idx = playlist.findIndex(s => String(s.id) === String(id));

        if (idx < 0) return;

        const wasCurrent = idx === currentIndex;

        playlist.splice(idx, 1);

        if (playlist.length === 0) {
            currentIndex = -1;
            audio.pause();
            audio.removeAttribute("src");
            updateNowPlaying(null);
        } else {
            if (idx < currentIndex) {
                currentIndex -= 1;
            } else if (wasCurrent) {
                currentIndex = Math.min(idx, playlist.length - 1);
                loadCurrent(false);
            }
        }

        renderPlaylist();
        refreshButtonsAndCovers();
    }

    function togglePlaylist(id) {
        const exists = playlist.some(s => String(s.id) === String(id));

        if (exists) {
            removeFromPlaylistById(id);
        } else {
            addToPlaylist(id);
        }
    }

    function coverClick(id) {
        const song = getSongById(id);

        if (!song) return;

        if (!playlist.some(s => String(s.id) === String(id))) {
            const added = addToPlaylist(id);
            if (!added) return;
        }

        const idx = playlist.findIndex(s => String(s.id) === String(id));

        if (idx < 0) return;

        if (currentIndex === idx) {
            togglePlay();
        } else {
            currentIndex = idx;
            loadCurrent(true);
        }
    }

    function renderPlaylist() {
        playlistCount.textContent = `${playlist.length} tracks`;

        if (playlist.length === 0) {
            playlistEl.innerHTML = `
                <div class="playlist-empty">
                    아직 플레이리스트가 비어 있습니다.<br>
                    오른쪽 랭킹에서 앨범 이미지나 체크 버튼을 눌러 추가하세요.
                </div>
            `;
            return;
        }

        playlistEl.innerHTML = playlist.map((song, idx) => {
            const active = idx === currentIndex ? "active" : "";
            const thumb = song.image_url
                ? `<img class="playlist-thumb" src="${escapeHtml(song.image_url)}" loading="lazy">`
                : `<div class="playlist-thumb"></div>`;

            return `
                <div class="playlist-item ${active}" data-action="play-playlist-index" data-index="${idx}">
                    ${thumb}
                    <div class="playlist-meta">
                        <div class="playlist-song-title">${escapeHtml(song.title)}</div>
                        <div class="playlist-song-sub">${escapeHtml(song.creator)} ${escapeHtml(song.handle || "")}</div>
                    </div>
                    <button class="remove-btn" data-action="remove-playlist" data-song-id="${escapeHtml(song.id)}">×</button>
                </div>
            `;
        }).join("");

        bindPlaylistEvents();
    }

    function refreshButtonsAndCovers() {
        document.querySelectorAll(".add-btn[data-song-id]").forEach(btn => {
            const id = btn.dataset.songId;
            const added = playlist.some(s => String(s.id) === String(id));

            if (added) {
                btn.classList.add("added");
                btn.textContent = "✓";
            } else {
                btn.classList.remove("added");
                btn.textContent = "+";
            }
        });

        document.querySelectorAll(".cover-btn[data-song-id]").forEach(cover => {
            const id = cover.dataset.songId;
            const song = getSongById(id);

            cover.classList.remove("playing");
            cover.classList.remove("paused");

            if (song && isCurrentSong(song)) {
                if (audio.paused) {
                    cover.classList.add("paused");
                } else {
                    cover.classList.add("playing");
                }
            }
        });
    }

    function playPlaylistIndex(idx) {
        if (idx < 0 || idx >= playlist.length) return;

        if (currentIndex === idx) {
            togglePlay();
        } else {
            currentIndex = idx;
            loadCurrent(true);
        }
    }

    function updateNowPlaying(song) {
        if (!song) {
            nowCoverWrap.innerHTML = `<div class="now-placeholder">No track selected</div>`;
            nowTitle.textContent = "플레이리스트에 곡을 추가하세요";
            nowCreator.textContent = "앨범 이미지나 체크 버튼을 누르면 추가됩니다.";
            nowStyleTags.innerHTML = "";
            lyricsPanel.textContent = "가사/프롬프트 정보가 있으면 여기에 표시됩니다.";
            lyricsPanel.classList.add("empty");
            playBtn.textContent = "▶";
            progress.value = 0;
            currentTimeEl.textContent = "0:00";
            durationEl.textContent = "0:00";
            refreshButtonsAndCovers();
            return;
        }

        if (song.image_url) {
            nowCoverWrap.innerHTML = `<img class="now-cover" src="${escapeHtml(song.image_url)}">`;
        } else {
            nowCoverWrap.innerHTML = `<div class="now-placeholder">No image</div>`;
        }

        nowTitle.textContent = song.title;
        nowCreator.textContent = `${song.creator || ""} ${song.handle || ""}`.trim();
        nowStyleTags.innerHTML = renderNowStyleTags(song.style_tags);

        if (song.lyrics && song.lyrics.trim()) {
            lyricsPanel.textContent = song.lyrics;
            lyricsPanel.classList.remove("empty");
        } else {
            lyricsPanel.textContent = "가사/프롬프트 정보가 아직 수집되지 않았습니다.";
            lyricsPanel.classList.add("empty");
        }

        refreshButtonsAndCovers();
    }

    function loadCurrent(autoplay) {
        if (currentIndex < 0 || currentIndex >= playlist.length) {
            updateNowPlaying(null);
            return;
        }

        const song = playlist[currentIndex];

        updateNowPlaying(song);
        renderPlaylist();

        if (!song.audio_url) {
            alert("이 곡에는 audio_url이 없습니다.");
            return;
        }

        audio.pause();
        audio.src = song.audio_url;
        audio.load();
        updateVolume();

        if (autoplay) {
            audio.play()
                .then(() => {
                    playBtn.textContent = "Ⅱ";
                    refreshButtonsAndCovers();
                })
                .catch(err => {
                    console.log(err);
                    playBtn.textContent = "▶";
                    refreshButtonsAndCovers();
                    alert("브라우저가 오디오 재생을 막았거나 URL을 재생할 수 없습니다.");
                });
        } else {
            playBtn.textContent = "▶";
            refreshButtonsAndCovers();
        }
    }

    function togglePlay() {
        if (currentIndex === -1) {
            if (playlist.length > 0) {
                currentIndex = 0;
                loadCurrent(true);
            }

            return;
        }

        if (audio.paused) {
            audio.play()
                .then(() => {
                    playBtn.textContent = "Ⅱ";
                    refreshButtonsAndCovers();
                })
                .catch(err => {
                    console.log(err);
                    alert("브라우저가 오디오 재생을 막았거나 URL을 재생할 수 없습니다.");
                });
        } else {
            audio.pause();
            playBtn.textContent = "▶";
            refreshButtonsAndCovers();
        }
    }

    function getRandomNextIndex() {
        if (playlist.length <= 1) return currentIndex;

        let next = currentIndex;

        while (next === currentIndex) {
            next = Math.floor(Math.random() * playlist.length);
        }

        return next;
    }

    function playNext() {
        if (playlist.length === 0) return;

        if (playbackMode === "shuffle") {
            currentIndex = getRandomNextIndex();
            loadCurrent(true);
            return;
        }

        if (currentIndex < playlist.length - 1) {
            currentIndex += 1;
            loadCurrent(true);
        } else if (repeatAll) {
            currentIndex = 0;
            loadCurrent(true);
        } else {
            audio.pause();
            playBtn.textContent = "▶";
            refreshButtonsAndCovers();
        }
    }

    function playPrev() {
        if (playlist.length === 0) return;

        if (audio.currentTime > 3) {
            audio.currentTime = 0;
            return;
        }

        if (playbackMode === "shuffle") {
            currentIndex = getRandomNextIndex();
            loadCurrent(true);
            return;
        }

        if (currentIndex > 0) {
            currentIndex -= 1;
            loadCurrent(true);
        } else if (repeatAll) {
            currentIndex = playlist.length - 1;
            loadCurrent(true);
        }
    }

    function refreshModeButtons() {
        repeatOneBtn.classList.toggle("active", repeatOne);
        repeatAllBtn.classList.toggle("active", repeatAll);
        sequenceBtn.classList.toggle("active", playbackMode === "sequence");
        shuffleBtn.classList.toggle("active", playbackMode === "shuffle");
    }

    playBtn.addEventListener("click", togglePlay);
    nextBtn.addEventListener("click", playNext);
    prevBtn.addEventListener("click", playPrev);

    repeatOneBtn.addEventListener("click", () => {
        repeatOne = !repeatOne;

        if (repeatOne) {
            repeatAll = false;
        }

        refreshModeButtons();
    });

    repeatAllBtn.addEventListener("click", () => {
        repeatAll = !repeatAll;

        if (repeatAll) {
            repeatOne = false;
        }

        refreshModeButtons();
    });

    sequenceBtn.addEventListener("click", () => {
        playbackMode = "sequence";
        refreshModeButtons();
    });

    shuffleBtn.addEventListener("click", () => {
        playbackMode = "shuffle";
        refreshModeButtons();
    });

    clearBtn.addEventListener("click", () => {
        playlist = [];
        currentIndex = -1;
        audio.pause();
        audio.removeAttribute("src");
        updateNowPlaying(null);
        renderPlaylist();
        refreshButtonsAndCovers();
    });

    volume.addEventListener("input", updateVolume);

    progress.addEventListener("input", () => {
        if (!isFinite(audio.duration) || audio.duration <= 0) return;

        audio.currentTime = (Number(progress.value) / 1000) * audio.duration;
    });

    audio.addEventListener("timeupdate", () => {
        if (isFinite(audio.duration) && audio.duration > 0) {
            progress.value = Math.round((audio.currentTime / audio.duration) * 1000);
            currentTimeEl.textContent = formatTime(audio.currentTime);
            durationEl.textContent = formatTime(audio.duration);
        }
    });

    audio.addEventListener("loadedmetadata", () => {
        durationEl.textContent = formatTime(audio.duration);
    });

    audio.addEventListener("play", () => {
        playBtn.textContent = "Ⅱ";
        refreshButtonsAndCovers();
    });

    audio.addEventListener("pause", () => {
        playBtn.textContent = "▶";
        refreshButtonsAndCovers();
    });

    audio.addEventListener("ended", () => {
        if (repeatOne) {
            audio.currentTime = 0;
            audio.play();
        } else {
            playNext();
        }
    });

    searchInput.addEventListener("input", () => {
        renderTable(searchInput.value);
    });

    function openRankingInfo(id) {
        const song = getSongById(id);

        if (!song) return;

        modalTitle.textContent = `#${song.rank} ${song.title}`;
        modalSub.textContent = `${song.creator || ""} ${song.handle || ""}`.trim();

        scoreTrend.textContent = formatFloat(song.trend_score);
        scoreBase.textContent = formatFloat(song.base_score);
        scoreGrowth.textContent = formatFloat(song.growth_score);
        scoreFreshness.textContent = formatFloat(song.freshness_score);

        rankingModal.classList.add("open");
        drawHistoryChart(id);
    }

    function drawHistoryChart(id) {
        const ctx = historyCanvas.getContext("2d");
        const w = historyCanvas.width;
        const h = historyCanvas.height;

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, w, h);

        const rows = histories[String(id)] || [];

        ctx.fillStyle = "#6b7280";
        ctx.font = "12px Arial";

        if (!rows.length) {
            ctx.fillText("히스토리 데이터가 아직 없습니다.", 20, 40);
            return;
        }

        const padL = 54;
        const padR = 18;
        const padT = 18;
        const padB = 36;
        const chartW = w - padL - padR;
        const chartH = h - padT - padB;

        const maxVal = Math.max(
            1,
            ...rows.map(r => Math.max(r.play_count || 0, r.upvote_count || 0, r.comment_count || 0))
        );

        function xAt(i) {
            if (rows.length <= 1) return padL;
            return padL + (i / (rows.length - 1)) * chartW;
        }

        function yAt(v) {
            return padT + chartH - ((v || 0) / maxVal) * chartH;
        }

        ctx.strokeStyle = "#e5e7eb";
        ctx.lineWidth = 1;

        for (let i = 0; i <= 4; i++) {
            const y = padT + (chartH / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(w - padR, y);
            ctx.stroke();

            const label = Math.round(maxVal - (maxVal / 4) * i);
            ctx.fillStyle = "#6b7280";
            ctx.fillText(formatInt(label), 6, y + 4);
        }

        function drawLine(key, color, label, labelX) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();

            rows.forEach((r, i) => {
                const x = xAt(i);
                const y = yAt(r[key]);

                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });

            ctx.stroke();

            ctx.fillStyle = color;
            ctx.fillText(label, labelX, 14);
        }

        drawLine("play_count", "#111827", "play", padL);
        drawLine("upvote_count", "#ef4444", "like", padL + 52);
        drawLine("comment_count", "#2563eb", "comment", padL + 100);

        ctx.fillStyle = "#6b7280";
        ctx.fillText(rows[0].checked_at || "", padL, h - 12);
        ctx.fillText(rows[rows.length - 1].checked_at || "", w - padR - 80, h - 12);
    }

    modalCloseBtn.addEventListener("click", () => {
        rankingModal.classList.remove("open");
    });

    rankingModal.addEventListener("click", event => {
        if (event.target === rankingModal) {
            rankingModal.classList.remove("open");
        }
    });

    function resetPlayerForTabSwitch() {
        playlist = [];
        currentIndex = -1;
        audio.pause();
        audio.removeAttribute("src");
        progress.value = 0;
        currentTimeEl.textContent = "0:00";
        durationEl.textContent = "0:00";
        updateNowPlaying(null);
        renderPlaylist();
        refreshButtonsAndCovers();
    }

    function setActiveTabButton(activeKey) {
        if (!rankViewTabs) return;
        rankViewTabs.querySelectorAll(".rank-view-tab").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.tabKey === activeKey);
        });
    }

    function activateRankTab(key, resetPlayer = true) {
        if (!tabsData || !tabsData[key]) return;

        const tab = tabsData[key] || {};
        songs = Array.isArray(tab.songs) ? tab.songs : [];
        histories = tab.histories || {};

        if (rankingTitle) rankingTitle.textContent = getTabTitle(key, tab);
        if (rankingSub) rankingSub.textContent = getTabDescription(key, tab);

        sortState = { key: null, direction: null };
        setActiveTabButton(key);

        if (searchInput) searchInput.value = "";
        if (resetPlayer) resetPlayerForTabSwitch();
        renderTable("");
    }

    function initRankTabs() {
        const hasTabs = tabsData && typeof tabsData === "object" && Array.isArray(tabsOrder) && tabsOrder.length > 0;

        if (!hasTabs || !rankViewTabs) {
            if (rankViewTabs) rankViewTabs.style.display = "none";
            return false;
        }

        rankViewTabs.innerHTML = "";

        tabsOrder.forEach(key => {
            const tab = tabsData[key];
            if (!tab) return;

            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "rank-view-tab";
            btn.dataset.tabKey = key;
            btn.textContent = getTabTitle(key, tab);
            btn.addEventListener("click", () => activateRankTab(key, true));
            rankViewTabs.appendChild(btn);
        });

        const initialKey = tabsData[defaultTabKey] ? defaultTabKey : tabsOrder.find(key => tabsData[key]);

        if (initialKey) {
            activateRankTab(initialKey, false);
            return true;
        }

        return false;
    }

    bindSortHeaderEvents();
    const tabsInitialized = initRankTabs();
    if (!tabsInitialized) {
        renderTable("");
    }
    renderPlaylist();
    refreshModeButtons();
    updateVolume();
    </script>
    """

    full_html = (
        html_template
        .replace("{title_html}", title_html)
        .replace("{subtitle_html}", subtitle_html)
        .replace("__SONGS_JSON__", songs_json)
        .replace("__HISTORIES_JSON__", histories_json)
        .replace("__RANKING_CONFIG_JSON__", ranking_config_json)
        .replace("__TABS_JSON__", tabs_json or "null")
        .replace("__TABS_ORDER_JSON__", tabs_order_json or "[]")
        .replace("__DEFAULT_TAB_KEY__", default_tab_key_js)
    )

    components.html(
        full_html,
        height=1500,
        scrolling=True,
    )


# ================================
# Main
# ================================

st.title("Suno Chart v1.03")
st.caption("Actions에서 미리 생성한 탭별 payload 기준으로 빠르게 표시합니다.")

if st.button("데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()

try:
    sync_remote_data_files(DATA_RAW_BASE_URL, GITHUB_RAW_TOKEN)
except Exception as e:
    st.warning(f"Remote data sync failed. Using existing local data files. Error: {e}")

payload_fingerprint = file_fingerprint(APP_PAYLOAD_ZIP_PATH)
payload, payload_error = load_app_payload(payload_fingerprint)

if payload:
    meta = payload.get("meta", {})
    tabs_payload = payload.get("tabs", {})

    total_songs = meta.get("active_song_count", 0)
    latest_created_txt = meta.get("newest_created_at", "-") or "-"
    last_checked_txt = meta.get("last_checked_at", "-") or "-"
    generated_at_txt = meta.get("generated_at", "-") or "-"

    left_top, right_top = st.columns([0.9, 1.1], gap="large")

    with left_top:
        st.markdown("### 데이터 정보")

        with st.container(border=True):
            row1_label, row1_value = st.columns([0.45, 0.55])
            with row1_label:
                st.caption("Active 곡 수")
            with row1_value:
                st.markdown(
                    f"<div style='text-align:right; font-size:15px; font-weight:800;'>{int(total_songs or 0):,}</div>",
                    unsafe_allow_html=True,
                )

            row2_label, row2_value = st.columns([0.45, 0.55])
            with row2_label:
                st.caption("최신 생성곡")
            with row2_value:
                st.markdown(
                    f"<div style='text-align:right; font-size:13px; font-weight:800; white-space:nowrap;'>{latest_created_txt}</div>",
                    unsafe_allow_html=True,
                )

            row3_label, row3_value = st.columns([0.45, 0.55])
            with row3_label:
                st.caption("마지막 업데이트")
            with row3_value:
                st.markdown(
                    f"<div style='text-align:right; font-size:13px; font-weight:800; white-space:nowrap;'>{last_checked_txt}</div>",
                    unsafe_allow_html=True,
                )

            row4_label, row4_value = st.columns([0.45, 0.55])
            with row4_label:
                st.caption("Payload 생성")
            with row4_value:
                st.markdown(
                    f"<div style='text-align:right; font-size:13px; font-weight:800; white-space:nowrap;'>{generated_at_txt}</div>",
                    unsafe_allow_html=True,
                )

    with right_top:
        st.markdown("### 수동 곡 추가")

        with st.container(border=True):
            with st.form("manual_add_song_form", clear_on_submit=True):
                manual_suno_url = st.text_input(
                    "Suno song link",
                    placeholder="https://suno.com/song/... 또는 https://suno.com/s/...",
                    label_visibility="collapsed",
                )

                submit_col1, submit_col2 = st.columns([0.28, 0.72])

                with submit_col1:
                    submitted = st.form_submit_button("곡정보수집 요청", use_container_width=True)

                with submit_col2:
                    st.caption("지원 링크: /song/... 또는 /s/...")

            if submitted:
                ok, msg = is_valid_suno_link(manual_suno_url)

                if not ok:
                    st.warning(msg)
                else:
                    ok, msg = queue_manual_song_url(manual_suno_url)

                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

    st.divider()

    tabs_order = payload.get("tabs_order") or ["new_songs", "top200", "rain_crew"]
    tabs_order = [key for key in tabs_order if key in tabs_payload]

    if not tabs_order:
        st.info("표시할 탭 payload가 없습니다.")
    else:
        # New Song / Top 200 / ☔rain crew 선택 버튼은 HTML 컴포넌트 내부의
        # {title_html} / {subtitle_html} 영역 바로 위에 렌더링된다.
        render_player_ranking_payload_tabs(
            tabs_payload,
            tabs_order=tabs_order,
            default_key="top200" if "top200" in tabs_order else tabs_order[0],
        )

    st.stop()

if payload_error:
    st.warning(payload_error)

# Payload가 아직 만들어지지 않은 첫 실행을 위한 기존 계산 fallback.
db_fingerprint = file_fingerprint(DB_ZIP_PATH)
history_fingerprint = file_fingerprint(HISTORY_ZIP_PATH)

raw_db, raw_hist, error = load_encrypted_data(
    db_fingerprint,
    history_fingerprint,
)

if error:
    st.error(error)
    st.stop()

if raw_db is None or raw_db.empty:
    st.warning("DB가 비어 있습니다. GitHub Actions가 신규곡을 수집한 뒤 다시 확인하세요.")
    st.stop()

db = prepare_db(raw_db)
hist = prepare_history(raw_hist)

scored = score_songs(
    db=db,
    hist=hist,
    play_weight=PLAY_WEIGHT,
    like_weight=LIKE_WEIGHT,
    comment_weight=COMMENT_WEIGHT,
    growth_weight=GROWTH_WEIGHT,
    freshness_weight=FRESHNESS_WEIGHT,
    growth_window_hours=GROWTH_WINDOW_HOURS,
    freshness_power=FRESHNESS_POWER,
)

active = filter_view(scored)
active = add_outlier_flags(active, sigma=OUTLIER_SIGMA, use_log=OUTLIER_USE_LOG)

new_view = active.sort_values("created_at", ascending=False, na_position="last").head(TOP_N).copy()
new_view = new_view.reset_index(drop=True)
new_view.insert(0, "rank", range(1, len(new_view) + 1))

top_view = active.sort_values("trend_score", ascending=False, na_position="last").head(TOP_N).copy()
top_view = top_view.reset_index(drop=True)
top_view.insert(0, "rank", range(1, len(top_view) + 1))

total_songs = len(db)
last_checked = db["last_checked_at"].max() if "last_checked_at" in db.columns else pd.NaT
newest_created = db["created_at"].max() if "created_at" in db.columns else pd.NaT

latest_created_txt = newest_created.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(newest_created) else "-"
last_checked_txt = last_checked.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(last_checked) else "-"

st.info("현재는 app payload가 없어 기존 계산 fallback으로 표시 중입니다. GitHub Actions가 한 번 실행되면 빨라집니다.")
st.markdown(f"**Active 곡 수:** {total_songs:,} · **최신 생성곡:** {latest_created_txt} · **마지막 업데이트:** {last_checked_txt}")
st.divider()

new_songs_payload = build_song_payload(new_view)
new_songs_histories = build_history_payload(hist, [song["id"] for song in new_songs_payload])

top200_payload = build_song_payload(top_view)
top200_histories = build_history_payload(hist, [song["id"] for song in top200_payload])

fallback_tabs = {
    "new_songs": {
        "title": "New Song",
        "description": "생성일 기준 최신순",
        "songs": new_songs_payload,
        "histories": new_songs_histories,
    },
    "top200": {
        "title": "Top 200",
        "description": "최근 4일 이내 곡 중 trend_score 상위 200",
        "songs": top200_payload,
        "histories": top200_histories,
    },
    "rain_crew": {
        "title": "☔rain crew",
        "description": "☔rain crew 탭은 app payload 생성 후 config/rain_crew.json 기준으로 표시됩니다.",
        "songs": [],
        "histories": {},
    },
}

render_player_ranking_payload_tabs(
    fallback_tabs,
    tabs_order=["new_songs", "top200", "rain_crew"],
    default_key="top200",
)
