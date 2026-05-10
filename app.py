import os
import sys
import pandas as pd
import streamlit as st

sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))
from secure_csv import decrypt_zip_to_file  # noqa: E402

DB_ZIP_PATH = "data/suno_song_db.zip"
HISTORY_ZIP_PATH = "data/suno_song_history.zip"
DATA_DIR = "data"

st.set_page_config(page_title="Suno Song Tracker", layout="wide")
st.title("Suno Song Tracker")

password = st.secrets.get("DATA_ZIP_PASSWORD")
if not password:
    st.error("DATA_ZIP_PASSWORD is missing from Streamlit secrets.")
    st.stop()

try:
    db_csv_path = decrypt_zip_to_file(DB_ZIP_PATH, DATA_DIR, password)
except Exception as exc:
    st.error(f"Failed to decrypt DB ZIP: {exc}")
    st.stop()

if not db_csv_path or not os.path.exists(db_csv_path):
    st.warning("Encrypted DB ZIP was not found or could not be extracted.")
    st.stop()

db = pd.read_csv(db_csv_path)
if db.empty:
    st.warning("DB is empty.")
    st.stop()

for col in ["created_at", "first_seen_at", "last_checked_at"]:
    if col in db.columns:
        db[col] = pd.to_datetime(db[col], errors="coerce", utc=True)

for col in ["play_count", "upvote_count", "comment_count", "flag_count", "duration"]:
    if col in db.columns:
        db[col] = pd.to_numeric(db[col], errors="coerce")

st.sidebar.header("Filters")

sort_candidates = [c for c in ["created_at", "play_count", "upvote_count", "comment_count", "last_checked_at"] if c in db.columns]
sort_by = st.sidebar.selectbox("Sort by", sort_candidates, index=0 if sort_candidates else None)
ascending = st.sidebar.checkbox("Ascending", value=False)
keyword = st.sidebar.text_input("Keyword in title/handle/display name", "")
hide_contest = st.sidebar.checkbox("Hide contest/remix contest", value=True)

view = db.copy()

if keyword.strip():
    k = keyword.strip().lower()
    mask = False
    for col in ["title", "handle", "display_name", "display_tags"]:
        if col in view.columns:
            mask = mask | view[col].astype(str).str.lower().str.contains(k, na=False)
    view = view[mask]

if hide_contest:
    if "is_contest_clip" in view.columns:
        view = view[view["is_contest_clip"].astype(str).str.lower() != "true"]
    if "download_disabled_reason" in view.columns:
        view = view[view["download_disabled_reason"].astype(str) != "remix_contest"]
    if "contest_ids" in view.columns:
        view = view[
            view["contest_ids"].isna()
            | (view["contest_ids"].astype(str).str.strip() == "")
            | (view["contest_ids"].astype(str).str.lower() == "nan")
            | (view["contest_ids"].astype(str).str.lower() == "none")
        ]

if sort_by and sort_by in view.columns:
    view = view.sort_values(sort_by, ascending=ascending, na_position="last")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total songs", len(db))
col2.metric("Visible songs", len(view))
if "last_checked_at" in db.columns:
    last_checked = db["last_checked_at"].max()
    col3.metric("Last checked", str(last_checked)[:19] if pd.notna(last_checked) else "-")
if "created_at" in db.columns:
    newest = db["created_at"].max()
    col4.metric("Newest created", str(newest)[:19] if pd.notna(newest) else "-")

st.subheader("Songs")

cols = [
    "title", "handle", "display_name", "created_at", "play_count",
    "upvote_count", "comment_count", "last_checked_at", "model",
    "display_tags", "song_url", "id",
]
cols = [c for c in cols if c in view.columns]
st.dataframe(view[cols], use_container_width=True, hide_index=True)

st.download_button(
    "Download current view CSV",
    data=view.to_csv(index=False, encoding="utf-8-sig"),
    file_name="suno_current_view.csv",
    mime="text/csv",
)

st.divider()
st.header("Growth history")

try:
    hist_csv_path = decrypt_zip_to_file(HISTORY_ZIP_PATH, DATA_DIR, password)
except Exception as exc:
    hist_csv_path = None
    st.info(f"History ZIP could not be decrypted: {exc}")

if hist_csv_path and os.path.exists(hist_csv_path):
    hist = pd.read_csv(hist_csv_path)

    if hist.empty:
        st.info("History is empty.")
    else:
        hist["checked_at"] = pd.to_datetime(hist["checked_at"], errors="coerce", utc=True)
        for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
            if col in hist.columns:
                hist[col] = pd.to_numeric(hist[col], errors="coerce")

        title_options = view[["id", "title", "handle"]].copy()
        title_options["label"] = (
            title_options["title"].fillna("(untitled)").astype(str)
            + " — @"
            + title_options["handle"].fillna("").astype(str)
            + " — "
            + title_options["id"].astype(str).str[:8]
        )

        selected_label = st.selectbox("Select song", title_options["label"].head(500).tolist())
        if selected_label:
            selected_id = title_options[title_options["label"] == selected_label]["id"].astype(str).iloc[0]
            h = hist[hist["id"].astype(str) == selected_id].copy().sort_values("checked_at")
            st.dataframe(h, use_container_width=True, hide_index=True)

            chart_cols = [c for c in ["play_count", "upvote_count", "comment_count"] if c in h.columns]
            if len(h) >= 2 and chart_cols:
                st.line_chart(h.set_index("checked_at")[chart_cols])
else:
    st.info("History ZIP not found.")
