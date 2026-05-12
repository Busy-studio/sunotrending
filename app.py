import os
import math
import json
import pandas as pd
import streamlit as st
from app_modules.data_loader import (
    APP_PAYLOAD_ZIP_PATH,
    DB_ZIP_PATH,
    HISTORY_ZIP_PATH,
    file_fingerprint,
    load_app_payload,
    load_encrypted_data,
    payload_to_df,
    sync_remote_data_files,
)
from app_modules.manual_queue import is_valid_suno_link, queue_manual_song_url
from app_modules.player_component import render_player_ranking_html
from app_modules.text_utils import (
    fix_mojibake,
    is_fake_rsc_token,
    normalize_handle,
    safe_float_or_none,
    safe_int_or_none,
    safe_text,
    safe_url,
)
from scripts.ranking_core import add_growth_features as core_add_growth_features, score_songs as core_score_songs


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


# Text/value helpers live in app_modules.text_utils.
# Data loading helpers live in app_modules.data_loader.

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
    "top200": "현재 날짜 기준 4일 이내 전체 DB 곡 중 trend_score 상위 200",
    "rain_crew": "☔rain crew 멤버 곡 최신순",
}

def display_tab_label(key, raw_title=None):
    title = clean_payload_text(raw_title or "")
    return title or TAB_LABELS.get(str(key), str(key).replace("_", " ").title())

def display_tab_description(key, raw_description=None):
    description = clean_payload_text(raw_description or "")
    return description or TAB_DESCRIPTIONS.get(str(key), "")


def inject_chart_selector_css():
    # Streamlit radio를 기존 HTML 내부 탭(.rank-view-tab)과 비슷한 pill 버튼 스타일로 보이게 만든다.
    st.markdown(
        """
        <style>
        div[data-testid="stRadio"] {
            margin: 0 0 8px 0;
        }

        div[data-testid="stRadio"] > label {
            display: none;
        }

        div[data-testid="stRadio"] div[role="radiogroup"] {
            display: flex;
            flex-direction: row;
            flex-wrap: wrap;
            gap: 7px;
            align-items: center;
            margin: 0 0 8px 0;
        }

        div[data-testid="stRadio"] div[role="radiogroup"] label {
            border: 1px solid #d1d5db;
            background: #ffffff;
            color: #6b7280;
            border-radius: 999px;
            padding: 7px 12px;
            font-size: 12px;
            font-weight: 900;
            cursor: pointer;
            transition: all 0.15s ease;
            min-height: auto;
            margin: 0;
        }

        div[data-testid="stRadio"] div[role="radiogroup"] label:hover {
            border-color: #ef4444;
            color: #ef4444;
        }

        div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) {
            background: #ef4444 !important;
            border-color: #ef4444 !important;
            color: #ffffff !important;
        }

        div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) p,
        div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) span {
            color: #ffffff !important;
        }

        div[data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {
            display: none;
        }

        div[data-testid="stRadio"] div[role="radiogroup"] label p {
            margin: 0;
            line-height: 1.2;
            font-size: 12px;
            font-weight: 900;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def choose_chart_key(tabs_payload, tabs_order, default_key="top200", widget_key="chart_view_selector"):
    tabs_payload = tabs_payload or {}
    tabs_order = [key for key in (tabs_order or list(tabs_payload.keys())) if key in tabs_payload]

    if not tabs_order:
        return None

    labels = []
    label_to_key = {}

    for key in tabs_order:
        tab = tabs_payload.get(key, {}) or {}
        label = display_tab_label(key, tab.get("title"))

        # 혹시 같은 표시명이 생겨도 radio 매핑이 깨지지 않게 방어
        if label in label_to_key:
            label = f"{label} ({key})"

        labels.append(label)
        label_to_key[label] = key

    if default_key not in tabs_order:
        default_key = tabs_order[0]

    default_label = next((label for label, key in label_to_key.items() if key == default_key), labels[0])
    default_index = labels.index(default_label) if default_label in labels else 0

    inject_chart_selector_css()

    selected_label = st.radio(
        "Chart",
        labels,
        index=default_index,
        horizontal=True,
        label_visibility="collapsed",
        key=widget_key,
    )

    return label_to_key.get(selected_label, default_key)


def choose_chart_key_above_ranking(tabs_payload, tabs_order, default_key="top200", widget_key="chart_view_selector"):
    # 왼쪽 플레이어 폭만큼 빈 칸을 두고, 오른쪽 랭킹 패널 위에만 차트 선택 pill을 표시한다.
    # 이렇게 하면 selector가 플레이리스트/플레이어 영역까지 침범하지 않는다.
    spacer_col, chart_col = st.columns([330, 1400], gap="small")

    with chart_col:
        return choose_chart_key(
            tabs_payload,
            tabs_order,
            default_key=default_key,
            widget_key=widget_key,
        )


def render_selected_payload_tab(tabs_payload, tabs_order=None, default_key="top200", widget_key="chart_view_selector"):
    tabs_payload = tabs_payload or {}
    tabs_order = [key for key in (tabs_order or list(tabs_payload.keys())) if key in tabs_payload]

    if not tabs_order:
        st.info("표시할 탭 payload가 없습니다.")
        return

    selected_key = choose_chart_key_above_ranking(
        tabs_payload,
        tabs_order,
        default_key=default_key if default_key in tabs_order else tabs_order[0],
        widget_key=widget_key,
    )

    if not selected_key or selected_key not in tabs_payload:
        st.info("선택한 차트 payload가 없습니다.")
        return

    tab = tabs_payload.get(selected_key, {}) or {}

    render_player_ranking_payload(
        tab.get("songs", []) or [],
        histories=tab.get("histories", {}) or {},
        title=display_tab_label(selected_key, tab.get("title")),
        subtitle=display_tab_description(selected_key, tab.get("description")),
    )

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




def restore_created_at_from_history_df(db, hist):
    """Fallback-mode repair: fill missing DB created_at from history before scoring."""
    if db is None or db.empty or hist is None or hist.empty:
        return db
    if "id" not in db.columns or "id" not in hist.columns or "created_at" not in hist.columns:
        return db

    db = db.copy()
    hist = hist.copy()

    if "created_at" not in db.columns:
        db["created_at"] = pd.NaT

    db["id"] = db["id"].astype(str)
    hist["id"] = hist["id"].astype(str)

    db_created = pd.to_datetime(db["created_at"], errors="coerce", utc=True)
    hist_created = pd.to_datetime(hist["created_at"], errors="coerce", utc=True)
    hist = hist.assign(__created_at_dt=hist_created).dropna(subset=["__created_at_dt"])

    if hist.empty:
        return db

    created_map = hist.groupby("id")["__created_at_dt"].min()
    missing = db_created.isna()
    restored = db.loc[missing, "id"].map(created_map)
    has_restored = restored.notna()

    if has_restored.any():
        db.loc[missing & has_restored, "created_at"] = restored[has_restored]

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
    """Fallback helper delegated to the shared ranking core."""
    return core_add_growth_features(db, hist, window_hours)

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
    """Fallback app scoring delegated to the shared ranking core.

    The normal app path uses the prebuilt payload. This fallback stays aligned with
    GitHub Actions scoring when payload loading is unavailable.
    """
    return core_score_songs(
        db=db,
        hist=hist,
        play_weight=play_weight,
        like_weight=like_weight,
        comment_weight=comment_weight,
        growth_weight=growth_weight,
        freshness_weight=freshness_weight,
        growth_window_hours=growth_window_hours,
        freshness_power=freshness_power,
    )

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


# ================================
# Main
# ================================

st.title("Suno Chart v1.04.3")
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
        # 플레이어와 차트를 하나의 HTML 컴포넌트 안에서 관리한다.
        # Streamlit radio/st.tabs로 차트를 바꾸면 전체 컴포넌트가 재마운트되어 <audio>가 끊기므로,
        # 탭 전환은 JS 내부에서 처리하고 왼쪽 플레이어 프레임은 그대로 유지한다.
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

raw_db = restore_created_at_from_history_df(raw_db, raw_hist)
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
        "description": "☔rain crew 멤버 곡 최신순",
        "songs": [],
        "histories": {},
    },
}

# fallback에서도 Streamlit radio 대신 HTML 내부 탭을 사용해서
# 차트를 바꿀 때 플레이어가 재마운트되지 않도록 한다.
render_player_ranking_payload_tabs(
    fallback_tabs,
    tabs_order=["new_songs", "top200", "rain_crew"],
    default_key="top200",
)
