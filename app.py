import os
import math
import html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from scripts.secure_csv import decrypt_zip_to_file

DB_ZIP_PATH = "data/suno_song_db.zip"
HISTORY_ZIP_PATH = "data/suno_song_history.zip"
DATA_DIR = "data"

RETENTION_HOURS = 96  # 4일
TOP_N_DEFAULT = 200


st.set_page_config(
    page_title="Suno Short-Term Trending",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ================================
# Text / encoding helpers
# ================================

def fix_mojibake(value):
    """
    Suno RSC에서 일부 다국어 텍스트가 UTF-8 bytes -> Latin-1처럼 깨져 들어오는 경우 보정.
    정상 한글/일본어/중국어는 그대로 유지.
    """
    if pd.isna(value):
        return ""

    s = str(value)

    if not s:
        return ""

    # 흔한 mojibake 패턴
    markers = [
        "Ã", "ã", "è", "é", "ê", "ë", "å", "ä", "Â",
        "Ð", "Ñ", "ç", "µ", "„", "”", "â", "ð", "", "", "Å"
    ]

    if not any(m in s for m in markers):
        return s

    candidates = [s]

    # 흔한 latin1/utf-8 깨짐 복구
    for enc in ["latin1", "cp1252"]:
        try:
            fixed = s.encode(enc, errors="ignore").decode("utf-8", errors="ignore")
            if fixed and fixed not in candidates:
                candidates.append(fixed)
        except Exception:
            pass

    # 가장 덜 깨져 보이는 후보 선택
    bad_chars = ["Ã", "ã", "Â", "â", "ð", "", "", "�", "Å"]

    def bad_score(x):
        return sum(x.count(ch) for ch in bad_chars)

    best = min(candidates, key=bad_score)

    return best or s


def esc(value):
    return html.escape(fix_mojibake(value))


def fmt_int(value):
    try:
        if pd.isna(value):
            return "0"
        return f"{int(float(value)):,}"
    except Exception:
        return "0"


def fmt_float(value, digits=1):
    try:
        if pd.isna(value):
            return "-"
        return f"{float(value):,.{digits}f}"
    except Exception:
        return "-"


def safe_url(value):
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.lower() in ["nan", "none", ""]:
        return ""
    return s


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

    text_cols = ["title", "handle", "display_name", "model", "display_tags"]
    for col in text_cols:
        if col in db.columns:
            db[col] = db[col].apply(fix_mojibake)

    for col in ["created_at", "first_seen_at", "last_checked_at"]:
        if col in db.columns:
            db[col] = pd.to_datetime(db[col], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col in db.columns:
            db[col] = pd.to_numeric(db[col], errors="coerce").fillna(0)

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


# ================================
# Filtering
# ================================

def filter_view(df, keyword, hide_contest, max_age_days):
    view = df.copy()

    if keyword.strip():
        k = keyword.strip().lower()
        mask = pd.Series(False, index=view.index)

        for col in ["title", "handle", "display_name"]:
            if col in view.columns:
                mask = mask | view[col].astype(str).str.lower().str.contains(k, na=False)

        view = view[mask]

    if hide_contest:
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

    if max_age_days and "created_at" in view.columns:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max_age_days)
        view = view[view["created_at"].isna() | (view["created_at"] >= cutoff)]

    return view


# ================================
# UI rendering
# ================================

def render_top_table(df):
    css = """
    <style>
    html, body {
        margin: 0;
        padding: 0;
        font-family: "Inter", "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic",
                     "Segoe UI", Arial, sans-serif;
        background: transparent;
        color: #fafafa;
    }

    .table-wrap {
        width: 100%;
        overflow-x: auto;
        background: transparent;
    }

    table.song-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        table-layout: fixed;
    }

    .song-table th {
        text-align: left;
        padding: 11px 8px;
        border-bottom: 1px solid rgba(160,160,160,0.35);
        background: rgba(120,120,120,0.16);
        position: sticky;
        top: 0;
        z-index: 2;
        font-weight: 700;
        color: #fafafa;
    }

    .song-table td {
        padding: 8px;
        border-bottom: 1px solid rgba(160,160,160,0.16);
        vertical-align: middle;
        color: #fafafa;
    }

    .song-table tr:hover {
        background: rgba(160,160,160,0.10);
    }

    .rank {
        font-weight: 800;
        font-size: 16px;
        text-align: right;
        width: 44px;
    }

    .cover {
        width: 56px;
        height: 56px;
        object-fit: cover;
        border-radius: 10px;
        background: rgba(160,160,160,0.18);
        display: block;
    }

    .empty-cover {
        width: 56px;
        height: 56px;
        border-radius: 10px;
        background: rgba(160,160,160,0.18);
    }

    .title-cell {
        overflow: hidden;
        word-break: break-word;
    }

    .title-link {
        font-weight: 800;
        text-decoration: none;
        color: #ffffff;
        display: inline-block;
        max-width: 100%;
        white-space: normal;
        line-height: 1.35;
    }

    .title-link:hover {
        text-decoration: underline;
    }

    .subtle {
        opacity: 0.70;
        font-size: 12px;
        margin-top: 4px;
        line-height: 1.25;
    }

    .creator {
        line-height: 1.35;
        word-break: break-word;
    }

    .num {
        text-align: right;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }

    .score {
        font-weight: 800;
        text-align: right;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
    }
    </style>
    """

    rows = []

    for _, r in df.iterrows():
        image = safe_url(r.get("image_url", ""))
        song_url = safe_url(r.get("song_url", ""))
        title = esc(r.get("title", "Untitled"))
        handle = esc(r.get("handle", ""))
        display_name = esc(r.get("display_name", ""))

        creator = display_name or handle
        if handle and display_name and handle.lower() not in display_name.lower():
            creator = f"{display_name}<div class='subtle'>@{handle}</div>"
        elif handle:
            creator = f"@{handle}"

        created_at = r.get("created_at")
        if pd.notna(created_at):
            created_txt = created_at.strftime("%Y-%m-%d %H:%M UTC")
        else:
            created_txt = "-"

        if image:
            img_html = f"<img class='cover' src='{html.escape(image)}' loading='lazy'>"
        else:
            img_html = "<div class='empty-cover'></div>"

        if song_url:
            title_html = (
                f"<a class='title-link' href='{html.escape(song_url)}' "
                f"target='_blank' rel='noopener noreferrer'>{title}</a>"
            )
        else:
            title_html = title

        rows.append(
            f"""
            <tr>
                <td class="rank">{int(r.get("rank", 0))}</td>
                <td>{img_html}</td>
                <td class="title-cell">
                    {title_html}
                    <div class="subtle">{created_txt}</div>
                </td>
                <td class="creator">{creator}</td>
                <td class="num">{fmt_int(r.get("play_count", 0))}</td>
                <td class="num">{fmt_int(r.get("upvote_count", 0))}</td>
                <td class="num">{fmt_int(r.get("comment_count", 0))}</td>
                <td class="score">{fmt_float(r.get("trend_score", 0), 1)}</td>
            </tr>
            """
        )

    table_html = f"""
    {css}
    <div class="table-wrap">
        <table class="song-table">
            <thead>
                <tr>
                    <th style="width:44px; text-align:right;">순위</th>
                    <th style="width:72px;">앨범</th>
                    <th>곡 제목</th>
                    <th style="width:190px;">원작자</th>
                    <th style="width:90px; text-align:right;">플레이</th>
                    <th style="width:90px; text-align:right;">좋아요</th>
                    <th style="width:80px; text-align:right;">댓글</th>
                    <th style="width:90px; text-align:right;">점수</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """

    height = min(12000, max(600, 92 + len(df) * 74))

    components.html(
        table_html,
        height=height,
        scrolling=True,
    )


# ================================
# Main
# ================================

st.title("Suno Short-Term Trending")
st.caption("최근 4일 생성곡 기준 · 30분/15분 단위 업데이트 · 누적 반응 + 최근 변화량 + 신선도 점수")

raw_db, raw_hist, error = load_encrypted_data()

if error:
    st.error(error)
    st.stop()

if raw_db is None or raw_db.empty:
    st.warning("DB가 비어 있습니다. GitHub Actions가 신규곡을 수집한 뒤 다시 확인하세요.")
    st.stop()

db = prepare_db(raw_db)
hist = prepare_history(raw_hist)

with st.sidebar:
    st.header("Ranking Settings")

    top_n = st.slider("표시 개수", min_value=20, max_value=500, value=TOP_N_DEFAULT, step=20)

    growth_window_hours = st.slider("변화량 계산 시간", min_value=1, max_value=24, value=3, step=1)

    max_age_days = st.slider("표시할 생성일 범위", min_value=1, max_value=4, value=4, step=1)

    st.divider()

    play_weight = st.slider("플레이 가중치", min_value=0.0, max_value=5.0, value=1.0, step=0.1)
    like_weight = st.slider("좋아요 가중치", min_value=0.0, max_value=8.0, value=3.0, step=0.1)
    comment_weight = st.slider("댓글 가중치", min_value=0.0, max_value=10.0, value=4.0, step=0.1)
    growth_weight = st.slider("최근 변화량 가중치", min_value=0.0, max_value=10.0, value=2.5, step=0.1)
    freshness_weight = st.slider("신선도 가중치", min_value=0.0, max_value=80.0, value=35.0, step=1.0)
    freshness_power = st.slider("신선도 감쇠 곡률", min_value=0.5, max_value=3.0, value=1.35, step=0.05)

    st.divider()

    keyword = st.text_input("검색", "")
    hide_contest = st.checkbox("콘테스트/캠페인 곡 숨기기", value=True)

scored = score_songs(
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

view = filter_view(scored, keyword, hide_contest, max_age_days)

view = view.sort_values("trend_score", ascending=False, na_position="last").head(top_n).copy()
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

tab1, tab2, tab3 = st.tabs(["Top 200", "Score Formula", "History"])

with tab1:
    render_top_table(view)

with tab2:
    st.subheader("현재 점수 공식")

    formula_text = (
        "base_score =\n"
        f"  log1p(play_count) × {play_weight}\n"
        f"+ log1p(upvote_count) × {like_weight}\n"
        f"+ log1p(comment_count) × {comment_weight}\n\n"
        "growth_score =\n"
        f"  (\n"
        f"    log1p(play_delta_{growth_window_hours}h) × 1.2\n"
        f"  + log1p(upvote_delta_{growth_window_hours}h) × 5.0\n"
        f"  + log1p(comment_delta_{growth_window_hours}h) × 8.0\n"
        f"  ) × {growth_weight}\n\n"
        "freshness =\n"
        f"  max(0, 1 - age_hours / 96) ^ {freshness_power}\n\n"
        "freshness_score =\n"
        f"  freshness × {freshness_weight}\n\n"
        "trend_score =\n"
        "  base_score + growth_score + freshness_score"
    )

    st.code(formula_text, language="text")

    st.markdown(
        """
- `created_at`은 Suno에서 곡이 생성된 시각입니다.
- `first_seen_at`은 수집기가 처음 발견한 시각입니다.
- `last_checked_at`은 수집기가 마지막으로 곡 페이지를 확인한 시각입니다.
- `growth_score`는 history CSV에 쌓인 기록을 사용합니다.
"""
    )

    formula_cols = [
        "rank",
        "title",
        "trend_score",
        "base_score",
        "growth_score",
        "freshness_score",
        "age_hours",
        "play_delta_window",
        "upvote_delta_window",
        "comment_delta_window",
    ]

    formula_cols = [c for c in formula_cols if c in view.columns]

    st.dataframe(
        view[formula_cols],
        use_container_width=True,
        hide_index=True,
    )


with tab3:
    if hist.empty:
        st.info("아직 history 데이터가 없습니다.")
    else:
        options = view[["id", "title", "handle"]].copy()
        options["label"] = (
            options["title"].fillna("(untitled)").astype(str)
            + " — @"
            + options["handle"].fillna("").astype(str)
        )

        if options.empty:
            st.info("표시 중인 곡이 없습니다.")
        else:
            selected = st.selectbox(
                "곡 선택",
                options["label"].tolist(),
            )

            selected_id = options.loc[
                options["label"] == selected,
                "id"
            ].iloc[0]

            h = hist[hist["id"].astype(str) == str(selected_id)].copy()
            h = h.sort_values("checked_at")

            if h.empty:
                st.info("선택한 곡의 history가 없습니다.")
            else:
                chart_cols = [
                    c for c in ["play_count", "upvote_count", "comment_count"]
                    if c in h.columns
                ]

                if chart_cols:
                    st.line_chart(h.set_index("checked_at")[chart_cols])

                st.dataframe(
                    h,
                    use_container_width=True,
                    hide_index=True,
                )
