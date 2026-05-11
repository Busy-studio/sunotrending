import os
import pandas as pd

from ranking_core import filter_active, prepare_db, prepare_history, score_songs

DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"
TOP_N = int(os.getenv("RANK_MOVEMENT_TOP_N", "200"))


def load_db():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Missing {DB_PATH}")
    db = pd.read_csv(DB_PATH)
    if "id" not in db.columns:
        raise RuntimeError("DB must contain id column")
    return prepare_db(db)


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return pd.DataFrame()
    return prepare_history(pd.read_csv(HISTORY_PATH))


def main():
    db = load_db()
    hist = load_history()

    print(f"[rank_movement] db_rows={len(db)}")
    print(f"[rank_movement] hist_rows={len(hist)}")

    old_current = {}
    has_previous_rank_data = False

    if "current_rank" in db.columns:
        old_rank_df = db[["id", "current_rank"]].copy()
        old_rank_df["current_rank"] = pd.to_numeric(old_rank_df["current_rank"], errors="coerce")
        has_previous_rank_data = old_rank_df["current_rank"].notna().any()
        old_current = dict(zip(old_rank_df["id"].astype(str), old_rank_df["current_rank"]))

    scored = score_songs(db, hist)
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
    ranked["current_score_new"] = ranked["trend_score"]
    ranked["base_score_new"] = ranked["base_score"]
    ranked["growth_score_new"] = ranked["growth_score"]
    ranked["freshness_score_new"] = ranked["freshness_score"]
    ranked["peak_play_count_new"] = ranked["play_count"]
    ranked["peak_upvote_count_new"] = ranked["upvote_count"]
    ranked["peak_comment_count_new"] = ranked["comment_count"]
    ranked["peak_adjusted_comment_count_new"] = ranked["effective_comment_count"]

    db = db.drop(
        columns=[
            "previous_rank", "current_rank", "rank_change", "rank_status",
            "current_score", "base_score", "growth_score", "freshness_score",
        ],
        errors="ignore",
    )

    merge_cols = [
        "id", "current_rank", "previous_rank", "rank_change", "rank_status",
        "current_score", "base_score", "growth_score", "freshness_score",
        "peak_play_count_new", "peak_upvote_count_new",
        "peak_comment_count_new", "peak_adjusted_comment_count_new",
    ]

    rank_updates = ranked.rename(columns={
        "new_current_rank": "current_rank",
        "previous_rank_new": "previous_rank",
        "rank_change_new": "rank_change",
        "rank_status_new": "rank_status",
        "current_score_new": "current_score",
        "base_score_new": "base_score",
        "growth_score_new": "growth_score",
        "freshness_score_new": "freshness_score",
    })[merge_cols]

    db = db.merge(rank_updates, on="id", how="left")

    now_text = pd.Timestamp.now(tz="UTC").isoformat()

    for col in [
        "best_rank", "best_trend_score", "best_score_at",
        "peak_play_count", "peak_upvote_count", "peak_comment_count", "peak_adjusted_comment_count",
    ]:
        if col not in db.columns:
            db[col] = pd.NA

    db["best_rank"] = pd.concat([
        pd.to_numeric(db["best_rank"], errors="coerce"),
        pd.to_numeric(db["current_rank"], errors="coerce"),
    ], axis=1).min(axis=1, skipna=True)

    old_best_score = pd.to_numeric(db["best_trend_score"], errors="coerce")
    current_score = pd.to_numeric(db["current_score"], errors="coerce")
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
            pd.to_numeric(db[peak_col], errors="coerce"),
            pd.to_numeric(db[new_col], errors="coerce"),
        ], axis=1).max(axis=1, skipna=True)

    db = db.drop(
        columns=[
            "peak_play_count_new", "peak_upvote_count_new",
            "peak_comment_count_new", "peak_adjusted_comment_count_new",
        ],
        errors="ignore",
    )

    db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")
    print(f"[rank_movement] saved db_rows={len(db)} -> {DB_PATH}")
    print(f"[rank_movement] ranked_rows={len(ranked)}")

    moved = ranked[ranked["rank_change_new"].notna() & (ranked["rank_change_new"] != 0)]
    print(f"[rank_movement] moved_rows={len(moved)}")


if __name__ == "__main__":
    main()
