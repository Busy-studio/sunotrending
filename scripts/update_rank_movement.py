import os
import pandas as pd

from ranking_core import filter_active, prepare_db, prepare_history, prepare_rankable_db, score_songs, serialize_datetime_columns_for_csv
from text_utils import normalize_text_columns

DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"
RANK_HISTORY_PATH = "data/suno_rank_history.csv"
TOP_N = int(os.getenv("RANK_MOVEMENT_TOP_N", "200"))

RANK_COLS = [
    "previous_rank", "current_rank", "rank_change", "rank_status",
    "current_score", "base_score", "growth_score", "freshness_score",
    "best_rank", "best_trend_score", "best_score_at",
    "peak_play_count", "peak_upvote_count", "peak_comment_count", "peak_adjusted_comment_count",
]


def dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Protect against exact duplicate column labels created by older rank merges."""
    if df.columns.duplicated().any():
        dupes = df.columns[df.columns.duplicated(keep=False)].tolist()
        print(f"[rank_movement] duplicate columns found, keeping last values: {dupes}")
        df = df.loc[:, ~df.columns.duplicated(keep="last")].copy()
    return df


def series_col(df: pd.DataFrame, col: str, default=pd.NA) -> pd.Series:
    """Return one Series even if a DataFrame has duplicate column names."""
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index)
    value = df[col]
    if isinstance(value, pd.DataFrame):
        return value.iloc[:, -1]
    return value


def numeric_col(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(series_col(df, col), errors="coerce")


def load_db() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Missing {DB_PATH}")
    db = pd.read_csv(DB_PATH)
    db = dedupe_columns(db)
    if "id" not in db.columns:
        raise RuntimeError("DB must contain id column")
    db = prepare_db(db)
    db = dedupe_columns(db)
    return db


def load_history() -> pd.DataFrame:
    if not os.path.exists(HISTORY_PATH):
        return pd.DataFrame()
    hist = pd.read_csv(HISTORY_PATH)
    hist = dedupe_columns(hist)
    return prepare_history(hist)




RANK_HISTORY_COLS = [
    "captured_at", "id", "rank",
    "trend_score", "base_score", "growth_score", "freshness_score",
    "play_count", "upvote_count", "comment_count", "adjusted_comment_count",
]


def append_rank_history(ranked: pd.DataFrame) -> None:
    """Append one lightweight Top-N chart snapshot and keep only active-window rows.

    This is intentionally a chart-entry history, not a full-song history.
    It stores only the current Top-N rows so archive can later summarize
    best rank, best score, and Top 10/50/200 appearances without growing too fast.
    """
    captured_at = pd.Timestamp.now(tz="UTC")

    if ranked is None or ranked.empty:
        print("[rank_history] skipped: no ranked rows")
        return

    snap = pd.DataFrame({
        "captured_at": captured_at.isoformat(),
        "id": ranked["id"].astype(str),
        "rank": pd.to_numeric(ranked["new_current_rank"], errors="coerce"),
        "trend_score": pd.to_numeric(ranked["trend_score"], errors="coerce"),
        "base_score": pd.to_numeric(ranked["base_score"], errors="coerce"),
        "growth_score": pd.to_numeric(ranked["growth_score"], errors="coerce"),
        "freshness_score": pd.to_numeric(ranked["freshness_score"], errors="coerce"),
        "play_count": pd.to_numeric(ranked.get("play_count"), errors="coerce"),
        "upvote_count": pd.to_numeric(ranked.get("upvote_count"), errors="coerce"),
        "comment_count": pd.to_numeric(ranked.get("comment_count"), errors="coerce"),
        "adjusted_comment_count": pd.to_numeric(ranked.get("effective_comment_count"), errors="coerce"),
    })

    if os.path.exists(RANK_HISTORY_PATH):
        try:
            old = pd.read_csv(RANK_HISTORY_PATH)
        except Exception as exc:
            print(f"[rank_history] failed to read old history, starting fresh: {exc}")
            old = pd.DataFrame(columns=RANK_HISTORY_COLS)
    else:
        old = pd.DataFrame(columns=RANK_HISTORY_COLS)

    for col in RANK_HISTORY_COLS:
        if col not in old.columns:
            old[col] = pd.NA
        if col not in snap.columns:
            snap[col] = pd.NA

    combined = pd.concat([old[RANK_HISTORY_COLS], snap[RANK_HISTORY_COLS]], ignore_index=True)
    combined["id"] = combined["id"].astype(str)
    combined["captured_at_dt"] = pd.to_datetime(combined["captured_at"], errors="coerce", utc=True)

    retention_days = int(os.getenv("SONG_RETENTION_DAYS", "4"))
    # Keep a small buffer so songs expiring near the cutoff can still be summarized.
    cutoff = captured_at - pd.Timedelta(days=max(retention_days, 1), hours=6)
    combined = combined[combined["captured_at_dt"].isna() | (combined["captured_at_dt"] >= cutoff)].copy()

    combined = combined.drop_duplicates(subset=["captured_at", "id"], keep="last")
    combined = combined.drop(columns=["captured_at_dt"], errors="ignore")
    combined = serialize_datetime_columns_for_csv(combined)
    combined.to_csv(RANK_HISTORY_PATH, index=False, encoding="utf-8-sig")

    print(
        f"[rank_history] appended={len(snap)}, rows={len(combined)}, "
        f"retention_days={retention_days} -> {RANK_HISTORY_PATH}"
    )

def main():
    db = load_db()
    hist = load_history()

    created_before = int(pd.to_datetime(db["created_at"], errors="coerce", utc=True).notna().sum()) if "created_at" in db.columns else 0
    db = prepare_rankable_db(db, hist)
    created_after = int(pd.to_datetime(db["created_at"], errors="coerce", utc=True).notna().sum()) if "created_at" in db.columns else 0
    print(f"[rank_movement] restored_created_at={created_after - created_before}, valid_created_at={created_after}/{len(db)}")

    print(f"[rank_movement] db_rows={len(db)}")
    print(f"[rank_movement] hist_rows={len(hist)}")

    old_current = {}
    has_previous_rank_data = False

    if "current_rank" in db.columns:
        current_rank_series = numeric_col(db, "current_rank")
        has_previous_rank_data = current_rank_series.notna().any()
        old_current = dict(zip(series_col(db, "id").astype(str), current_rank_series))

    scored = score_songs(db, hist)
    scored = dedupe_columns(scored)
    ranked = filter_active(scored).sort_values("trend_score", ascending=False, na_position="last").head(TOP_N).copy()
    ranked = ranked.reset_index(drop=True)
    ranked["new_current_rank"] = range(1, len(ranked) + 1)

    ranked["previous_rank_new"] = ranked["id"].astype(str).map(old_current)
    ranked["rank_change_new"] = ranked["previous_rank_new"] - ranked["new_current_rank"]

    def get_rank_status(row):
        if not has_previous_rank_data:
            return ""
        if pd.isna(row["previous_rank_new"]):
            return "new"
        if pd.isna(row["rank_change_new"]) or float(row["rank_change_new"]) == 0:
            return "same"
        if float(row["rank_change_new"]) > 0:
            return "up"
        return "down"

    ranked["rank_status_new"] = ranked.apply(get_rank_status, axis=1)

    append_rank_history(ranked)

    # Remove old rank/score columns before merging the new clean result.
    db = db.drop(columns=[c for c in RANK_COLS if c in db.columns], errors="ignore")
    db = dedupe_columns(db)

    rank_updates = pd.DataFrame({
        "id": ranked["id"].astype(str),
        "current_rank": ranked["new_current_rank"],
        "previous_rank": ranked["previous_rank_new"],
        "rank_change": ranked["rank_change_new"],
        "rank_status": ranked["rank_status_new"],
        "current_score": ranked["trend_score"],
        "base_score": ranked["base_score"],
        "growth_score": ranked["growth_score"],
        "freshness_score": ranked["freshness_score"],
        "peak_play_count_new": ranked["play_count"],
        "peak_upvote_count_new": ranked["upvote_count"],
        "peak_comment_count_new": ranked["comment_count"],
        "peak_adjusted_comment_count_new": ranked["effective_comment_count"],
    })

    db["id"] = db["id"].astype(str)
    db = db.merge(rank_updates, on="id", how="left", validate="one_to_one")
    db = dedupe_columns(db)

    now_text = pd.Timestamp.now(tz="UTC").isoformat()

    for col in [
        "best_rank", "best_trend_score", "best_score_at",
        "peak_play_count", "peak_upvote_count", "peak_comment_count", "peak_adjusted_comment_count",
    ]:
        if col not in db.columns:
            db[col] = pd.NA

    db["best_rank"] = pd.concat([
        numeric_col(db, "best_rank"),
        numeric_col(db, "current_rank"),
    ], axis=1).min(axis=1, skipna=True)

    old_best_score = numeric_col(db, "best_trend_score")
    current_score = numeric_col(db, "current_score")
    improved_mask = current_score.notna() & (old_best_score.isna() | (current_score > old_best_score))
    db["best_trend_score"] = pd.concat([old_best_score, current_score], axis=1).max(axis=1, skipna=True)
    db.loc[improved_mask, "best_score_at"] = now_text

    for peak_col, new_col in [
        ("peak_play_count", "peak_play_count_new"),
        ("peak_upvote_count", "peak_upvote_count_new"),
        ("peak_comment_count", "peak_comment_count_new"),
        ("peak_adjusted_comment_count", "peak_adjusted_comment_count_new"),
    ]:
        db[peak_col] = pd.concat([
            numeric_col(db, peak_col),
            numeric_col(db, new_col),
        ], axis=1).max(axis=1, skipna=True)

    db = db.drop(
        columns=[
            "peak_play_count_new", "peak_upvote_count_new",
            "peak_comment_count_new", "peak_adjusted_comment_count_new",
        ],
        errors="ignore",
    )
    db = dedupe_columns(db)

    db = normalize_text_columns(db)
    db = serialize_datetime_columns_for_csv(db)
    db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")
    print(f"[rank_movement] saved db_rows={len(db)} -> {DB_PATH}")
    print(f"[rank_movement] ranked_rows={len(ranked)}")

    moved = ranked[ranked["rank_change_new"].notna() & (ranked["rank_change_new"] != 0)]
    print(f"[rank_movement] moved_rows={len(moved)}")


if __name__ == "__main__":
    main()
