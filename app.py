import os
import math
import html
import json
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
DATA_DIR = "data"

RETENTION_HOURS = 96  # 4일
TOP_N = 200

# 고정 랭킹 설정
GROWTH_WINDOW_HOURS = 3
MAX_AGE_DAYS = 4
HIDE_CONTEST = True

PLAY_WEIGHT = 1.0
LIKE_WEIGHT = 3.0
COMMENT_WEIGHT = 4.0
GROWTH_WEIGHT = 2.5
FRESHNESS_WEIGHT = 35.0
FRESHNESS_POWER = 1.35


st.set_page_config(
    page_title="Suno Short-Term Trending",
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
        "ç", "è", "é", "ê", "ë", "í", "ì", "Å", "�",
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


def safe_url(value):
    if pd.isna(value):
        return ""

    s = str(value).strip()

    if s.lower() in ["nan", "none", ""]:
        return ""

    return s


def fmt_int(value):
    try:
        if pd.isna(value):
            return "0"
        return f"{int(float(value)):,}"
    except Exception:
        return "0"


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


# ================================
# Data loading
# ================================

@st.cache_data(ttl=300)
def load_encrypted_data():
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
    ]

    for col in text_cols:
        if col in db.columns:
            db[col] = db[col].apply(fix_mojibake)

    for col in ["created_at", "first_seen_at", "last_checked_at"]:
        if col in db.columns:
            db[col] = pd.to_datetime(db[col], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col in db.columns:
            db[col] = pd.to_numeric(db[col], errors="coerce").fillna(0)
        else:
            db[col] = 0

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

    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(hours=window_hours)

    recent = hist[hist["checked_at"] >= cutoff].copy()

    if recent.empty:
        return db

    agg_rows = []

    for song_id, g in recent.groupby("id"):
        g = g.sort_values("checked_at")

        if len(g) < 2:
            continue

        first = g.iloc[0]
        last = g.iloc[-1]

        hours = (last["checked_at"] - first["checked_at"]).total_seconds() / 3600

        if hours <= 0:
            hours = max(window_hours, 1)

        play_delta = max(0, float(last.get("play_count", 0)) - float(first.get("play_count", 0)))
        upvote_delta = max(0, float(last.get("upvote_count", 0)) - float(first.get("upvote_count", 0)))
        comment_delta = max(0, float(last.get("comment_count", 0)) - float(first.get("comment_count", 0)))

        agg_rows.append({
            "id": str(song_id),
            "play_delta_window": play_delta,
            "upvote_delta_window": upvote_delta,
            "comment_delta_window": comment_delta,
            "play_velocity_per_hour": play_delta / hours,
            "upvote_velocity_per_hour": upvote_delta / hours,
            "comment_velocity_per_hour": comment_delta / hours,
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
        if col in db.columns:
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

    view["base_score"] = (
        play_weight * view["play_count"].apply(lambda x: math.log1p(max(0, x)))
        + like_weight * view["upvote_count"].apply(lambda x: math.log1p(max(0, x)))
        + comment_weight * view["comment_count"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score_raw"] = (
        1.2 * view["play_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 5.0 * view["upvote_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 8.0 * view["comment_delta_window"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score"] = view["growth_score_raw"] * growth_weight

    view["trend_score"] = (
        view["base_score"]
        + view["growth_score"]
        + view["freshness_score"]
    )

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

        # display_tags는 장르/스타일 태그라서 제외
        # 실제 가사/프롬프트 후보만 표시
        for col in ["lyrics", "prompt", "gpt_description_prompt"]:
            if col in r.index:
                txt = safe_text(r.get(col, ""))

                if txt:
                    lyrics_candidates.append(txt)

        lyrics_text = "\n\n".join(lyrics_candidates)

        songs.append({
            "rank": int(r.get("rank", 0)),
            "id": safe_text(r.get("id", "")),
            "title": safe_text(r.get("title", "Untitled")) or "Untitled",
            "creator": display_name,
            "handle": handle_text,
            "created_at": created_txt,
            "play_count": int(float(r.get("play_count", 0) or 0)),
            "upvote_count": int(float(r.get("upvote_count", 0) or 0)),
            "comment_count": int(float(r.get("comment_count", 0) or 0)),
            "song_url": safe_url(r.get("song_url", "")),
            "audio_url": safe_url(r.get("audio_url", "")),
            "image_url": safe_url(r.get("image_url", "")),
            "lyrics": lyrics_text,
        })

    return songs


# ================================
# Player + ranking component
# ================================

def render_player_ranking(df):
    songs = build_song_payload(df)
    songs_json = json.dumps(songs, ensure_ascii=False).replace("</", "<\\/")

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

    * {
        box-sizing: border-box;
    }

    html, body {
        margin: 0;
        padding: 0;
        background: var(--bg);
        color: var(--text);
        font-family:
            "Noto Sans KR",
            "Noto Sans",
            "Apple SD Gothic Neo",
            "Malgun Gothic",
            "Segoe UI",
            "Segoe UI Symbol",
            "Apple Color Emoji",
            "Noto Color Emoji",
            Arial,
            sans-serif;
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
        margin-bottom: 10px;
        word-break: break-word;
    }

    .progress-wrap {
        margin: 10px 0 8px 0;
    }

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

    .ctrl-btn.active {
        background: #fee2e2;
        border-color: var(--accent);
        color: var(--accent-dark);
    }

    .ctrl-btn:hover {
        border-color: var(--accent);
    }

    .small-actions {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-bottom: 12px;
    }

    .small-btn {
        border: 1px solid var(--line-dark);
        background: white;
        color: var(--text);
        border-radius: 10px;
        padding: 8px 9px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 700;
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

    .playlist-item:last-child {
        border-bottom: 0;
    }

    .playlist-item.active {
        background: #fee2e2;
    }

    .playlist-thumb {
        width: 34px;
        height: 34px;
        border-radius: 8px;
        object-fit: cover;
        background: #e5e7eb;
    }

    .playlist-meta {
        overflow: hidden;
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

    .lyrics-panel.empty {
        color: var(--muted);
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
        min-width: 240px;
        outline: none;
    }

    .search-input:focus {
        border-color: var(--accent);
    }

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

    .song-table tr:hover {
        background: #f9fafb;
    }

    .rank {
        font-weight: 850;
        font-size: 16px;
        text-align: right;
    }

    .cover-cell {
        display: flex;
        gap: 7px;
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

    @media (max-width: 980px) {
        .app-shell {
            grid-template-columns: 1fr;
        }

        .player-panel {
            position: relative;
            height: auto;
            max-height: none;
        }

        .playlist {
            height: 220px;
        }

        .lyrics-panel {
            height: 180px;
        }
    }
    </style>

    <div class="app-shell">
        <aside class="player-panel">
            <div class="now-cover-wrap" id="nowCoverWrap">
                <div class="now-placeholder">No track selected</div>
            </div>

            <div class="now-title" id="nowTitle">플레이리스트에 곡을 추가하세요</div>
            <div class="now-creator" id="nowCreator">앨범 이미지나 + 버튼을 누르면 추가됩니다.</div>

            <div class="lyrics-panel empty" id="lyricsPanel">
                가사/프롬프트 정보가 있으면 여기에 표시됩니다.
            </div>

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

            <div class="small-actions">
                <button class="small-btn" id="repeatOneBtn">한 곡 반복</button>
                <button class="small-btn active" id="repeatAllBtn">전체 반복</button>
            </div>

            <div class="small-actions">
                <button class="small-btn" id="clearBtn">Playlist clear</button>
                <button class="small-btn" id="openBtn">Open Suno</button>
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
                    오른쪽 랭킹에서 앨범 이미지나 + 버튼을 눌러 추가하세요.
                </div>
            </div>

        </aside>

        <main class="ranking-panel">
            <div class="ranking-topbar">
                <div>
                    <div class="ranking-title">Top 200 Trending</div>
                    <div class="ranking-sub">앨범 이미지를 누르면 플레이리스트에 추가하고 바로 재생합니다.</div>
                </div>
                <input class="search-input" id="searchInput" placeholder="Search title / creator / handle">
            </div>

            <div class="table-wrap">
                <table class="song-table">
                    <thead>
                        <tr>
                            <th style="width:44px; text-align:right;">순위</th>
                            <th style="width:112px;">앨범</th>
                            <th>곡 제목</th>
                            <th style="width:210px;">원작자</th>
                            <th style="width:90px; text-align:right;">플레이</th>
                            <th style="width:90px; text-align:right;">좋아요</th>
                            <th style="width:80px; text-align:right;">댓글</th>
                        </tr>
                    </thead>
                    <tbody id="songTableBody"></tbody>
                </table>
            </div>
        </main>
    </div>

    <script>
    const songs = __SONGS_JSON__;

    let playlist = [];
    let currentIndex = -1;
    let audio = new Audio();

    let repeatOne = false;
    let repeatAll = true;

    const nowCoverWrap = document.getElementById("nowCoverWrap");
    const nowTitle = document.getElementById("nowTitle");
    const nowCreator = document.getElementById("nowCreator");
    const playlistEl = document.getElementById("playlist");
    const playlistCount = document.getElementById("playlistCount");
    const lyricsPanel = document.getElementById("lyricsPanel");

    const playBtn = document.getElementById("playBtn");
    const prevBtn = document.getElementById("prevBtn");
    const nextBtn = document.getElementById("nextBtn");
    const repeatOneBtn = document.getElementById("repeatOneBtn");
    const repeatAllBtn = document.getElementById("repeatAllBtn");
    const clearBtn = document.getElementById("clearBtn");
    const openBtn = document.getElementById("openBtn");
    const volume = document.getElementById("volume");
    const volumeText = document.getElementById("volumeText");
    const progress = document.getElementById("progress");
    const currentTimeEl = document.getElementById("currentTime");
    const durationEl = document.getElementById("duration");
    const searchInput = document.getElementById("searchInput");
    const songTableBody = document.getElementById("songTableBody");

    function escapeHtml(text) {
        if (text === null || text === undefined) return "";

        return String(text)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function formatInt(n) {
        try {
            return Number(n || 0).toLocaleString();
        } catch (e) {
            return "0";
        }
    }

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) return "0:00";

        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);

        return `${m}:${String(s).padStart(2, "0")}`;
    }

    function updateVolume() {
        const v = Number(volume.value || 80) / 100;
        volumeText.textContent = `${Math.round(v * 100)}%`;
        audio.volume = v;
    }

    function renderTable(filterText = "") {
        const q = filterText.trim().toLowerCase();

        const filtered = songs.filter(song => {
            if (!q) return true;

            const hay = [
                song.title,
                song.creator,
                song.handle
            ].join(" ").toLowerCase();

            return hay.includes(q);
        });

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

            return `
                <tr data-song-id="${escapeHtml(song.id)}">
                    <td class="rank">${song.rank}</td>
                    <td>
                        <div class="cover-cell">
                            <button class="cover-btn" onclick="addAndPlay('${escapeHtml(song.id)}')" title="추가 후 재생">
                                ${imageHtml}
                            </button>
                            <button class="add-btn" id="add-${escapeHtml(song.id)}" onclick="addToPlaylist('${escapeHtml(song.id)}')" title="플레이리스트 추가">+</button>
                        </div>
                    </td>
                    <td class="title-cell">
                        ${titleHtml}
                        <div class="subtle">${escapeHtml(song.created_at)}</div>
                    </td>
                    <td class="creator">
                        ${escapeHtml(song.creator)}
                        ${handleHtml}
                    </td>
                    <td class="num">${formatInt(song.play_count)}</td>
                    <td class="num">${formatInt(song.upvote_count)}</td>
                    <td class="num">${formatInt(song.comment_count)}</td>
                </tr>
            `;
        }).join("");

        refreshAddButtons();
    }

    function getSongById(id) {
        return songs.find(s => String(s.id) === String(id));
    }

    function addToPlaylist(id) {
        const song = getSongById(id);

        if (!song) return;

        if (!song.audio_url) {
            alert("이 곡에는 audio_url이 없습니다.");
            return;
        }

        if (!playlist.some(s => String(s.id) === String(song.id))) {
            playlist.push(song);
        }

        if (currentIndex === -1) {
            currentIndex = playlist.findIndex(s => String(s.id) === String(song.id));
            loadCurrent(false);
        }

        renderPlaylist();
        refreshAddButtons();
    }

    function addAndPlay(id) {
        addToPlaylist(id);

        const idx = playlist.findIndex(s => String(s.id) === String(id));

        if (idx >= 0) {
            currentIndex = idx;
            loadCurrent(true);
        }
    }

    window.addToPlaylist = addToPlaylist;
    window.addAndPlay = addAndPlay;

    function removeFromPlaylist(id, event) {
        if (event) event.stopPropagation();

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
        refreshAddButtons();
    }

    window.removeFromPlaylist = removeFromPlaylist;

    function renderPlaylist() {
        playlistCount.textContent = `${playlist.length} tracks`;

        if (playlist.length === 0) {
            playlistEl.innerHTML = `
                <div class="playlist-empty">
                    아직 플레이리스트가 비어 있습니다.<br>
                    오른쪽 랭킹에서 앨범 이미지나 + 버튼을 눌러 추가하세요.
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
                <div class="playlist-item ${active}" onclick="playPlaylistIndex(${idx})">
                    ${thumb}
                    <div class="playlist-meta">
                        <div class="playlist-song-title">${escapeHtml(song.title)}</div>
                        <div class="playlist-song-sub">${escapeHtml(song.creator)} ${escapeHtml(song.handle || "")}</div>
                    </div>
                    <button class="remove-btn" onclick="removeFromPlaylist('${escapeHtml(song.id)}', event)">×</button>
                </div>
            `;
        }).join("");
    }

    function refreshAddButtons() {
        songs.forEach(song => {
            const btn = document.getElementById(`add-${song.id}`);

            if (!btn) return;

            const added = playlist.some(s => String(s.id) === String(song.id));

            if (added) {
                btn.classList.add("added");
                btn.textContent = "✓";
            } else {
                btn.classList.remove("added");
                btn.textContent = "+";
            }
        });
    }

    function playPlaylistIndex(idx) {
        if (idx < 0 || idx >= playlist.length) return;

        currentIndex = idx;
        loadCurrent(true);
    }

    window.playPlaylistIndex = playPlaylistIndex;

    function updateNowPlaying(song) {
        if (!song) {
            nowCoverWrap.innerHTML = `<div class="now-placeholder">No track selected</div>`;
            nowTitle.textContent = "플레이리스트에 곡을 추가하세요";
            nowCreator.textContent = "앨범 이미지나 + 버튼을 누르면 추가됩니다.";
            lyricsPanel.textContent = "가사/프롬프트 정보가 있으면 여기에 표시됩니다.";
            lyricsPanel.classList.add("empty");
            playBtn.textContent = "▶";
            progress.value = 0;
            currentTimeEl.textContent = "0:00";
            durationEl.textContent = "0:00";
            return;
        }

        if (song.image_url) {
            nowCoverWrap.innerHTML = `<img class="now-cover" src="${escapeHtml(song.image_url)}">`;
        } else {
            nowCoverWrap.innerHTML = `<div class="now-placeholder">No image</div>`;
        }

        nowTitle.textContent = song.title;
        nowCreator.textContent = `${song.creator || ""} ${song.handle || ""}`.trim();

        if (song.lyrics && song.lyrics.trim()) {
            lyricsPanel.textContent = song.lyrics;
            lyricsPanel.classList.remove("empty");
        } else {
            lyricsPanel.textContent = "가사/프롬프트 정보가 아직 수집되지 않았습니다.";
            lyricsPanel.classList.add("empty");
        }
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
                })
                .catch(err => {
                    console.log(err);
                    playBtn.textContent = "▶";
                    alert("브라우저가 오디오 재생을 막았거나 URL을 재생할 수 없습니다.");
                });
        } else {
            playBtn.textContent = "▶";
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
                })
                .catch(err => {
                    console.log(err);
                    alert("브라우저가 오디오 재생을 막았거나 URL을 재생할 수 없습니다.");
                });
        } else {
            audio.pause();
            playBtn.textContent = "▶";
        }
    }

    function playNext() {
        if (playlist.length === 0) return;

        if (currentIndex < playlist.length - 1) {
            currentIndex += 1;
            loadCurrent(true);
        } else if (repeatAll) {
            currentIndex = 0;
            loadCurrent(true);
        } else {
            audio.pause();
            playBtn.textContent = "▶";
        }
    }

    function playPrev() {
        if (playlist.length === 0) return;

        if (audio.currentTime > 3) {
            audio.currentTime = 0;
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

    playBtn.addEventListener("click", togglePlay);
    nextBtn.addEventListener("click", playNext);
    prevBtn.addEventListener("click", playPrev);

    repeatOneBtn.addEventListener("click", () => {
        repeatOne = !repeatOne;

        if (repeatOne) {
            repeatAll = false;
        }

        repeatOneBtn.classList.toggle("active", repeatOne);
        repeatAllBtn.classList.toggle("active", repeatAll);
    });

    repeatAllBtn.addEventListener("click", () => {
        repeatAll = !repeatAll;

        if (repeatAll) {
            repeatOne = false;
        }

        repeatOneBtn.classList.toggle("active", repeatOne);
        repeatAllBtn.classList.toggle("active", repeatAll);
    });

    clearBtn.addEventListener("click", () => {
        playlist = [];
        currentIndex = -1;
        audio.pause();
        audio.removeAttribute("src");
        updateNowPlaying(null);
        renderPlaylist();
        refreshAddButtons();
    });

    openBtn.addEventListener("click", () => {
        if (currentIndex < 0 || currentIndex >= playlist.length) return;

        const song = playlist[currentIndex];

        if (song.song_url) {
            window.open(song.song_url, "_blank", "noopener,noreferrer");
        }
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
    });

    audio.addEventListener("pause", () => {
        playBtn.textContent = "▶";
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

    renderTable("");
    renderPlaylist();
    updateVolume();
    </script>
    """

    full_html = html_template.replace("__SONGS_JSON__", songs_json)

    components.html(
        full_html,
        height=1500,
        scrolling=True,
    )


# ================================
# Main
# ================================

st.title("Suno Short-Term Trending")
st.caption("최근 4일 생성곡 기준 · 누적 반응 + 최근 변화량 + 신선도 반영")

raw_db, raw_hist, error = load_encrypted_data()

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

view = filter_view(scored)

view = view.sort_values("trend_score", ascending=False, na_position="last").head(TOP_N).copy()
view = view.reset_index(drop=True)
view.insert(0, "rank", range(1, len(view) + 1))

total_songs = len(db)
visible_songs = len(view)
last_checked = db["last_checked_at"].max() if "last_checked_at" in db.columns else pd.NaT
newest_created = db["created_at"].max() if "created_at" in db.columns else pd.NaT

m1, m2, m3, m4 = st.columns(4)
m1.metric("DB 곡 수", f"{total_songs:,}")
m2.metric("표시 곡 수", f"{visible_songs:,}")
m3.metric("최신 생성곡", newest_created.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(newest_created) else "-")
m4.metric("마지막 업데이트", last_checked.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(last_checked) else "-")

st.divider()

render_player_ranking(view)
