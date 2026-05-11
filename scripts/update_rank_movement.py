import os
import math
import pandas as pd


DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"

RETENTION_HOURS = 96
MAX_AGE_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))
TOP_N = int(os.getenv("RANK_MOVEMENT_TOP_N", "200"))

GROWTH_WINDOW_HOURS = int(os.getenv("GROWTH_WINDOW_HOURS", "3"))

PLAY_WEIGHT = float(os.getenv("PLAY_WEIGHT", "1.0"))
LIKE_WEIGHT = float(os.getenv("LIKE_WEIGHT", "3.0"))
COMMENT_WEIGHT = float(os.getenv("COMMENT_WEIGHT", "4.0"))
GROWTH_WEIGHT = float(os.getenv("GROWTH_WEIGHT", "1.5"))
FRESHNESS_WEIGHT = float(os.getenv("FRESHNESS_WEIGHT", "35.0"))
FRESHNESS_POWER = float(os.getenv("FRESHNESS_POWER", "1.35"))


def to_number(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def load_db():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Missing {DB_PATH}")

    db = pd.read_csv(DB_PATH)

    if "id" not in db.columns:
        raise RuntimeError("DB must contain id column")

    db["id"] = db["id"].astype(str)

    for col in [
        "play_count",
        "upvote_count",
        "comment_count",
        "adjusted_comment_count",
        "flag_count",
        "current_rank",
        "previous_rank",
        "rank_change",
    ]:
        if col in db.columns:
            db[col] = pd.to_numeric(db[col], errors="coerce")
        else:
            db[col] = pd.NA

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        db[col] = db[col].fillna(0)

    for col in ["created_at", "first_seen_at", "last_checked_at"]:
        if col in db.columns:
            db[col] = pd.to_datetime(db[col], errors="coerce", utc=True)

    return db


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return pd.DataFrame()

    hist = pd.read_csv(HISTORY_PATH)

    if hist.empty:
        return hist

    if "id" in hist.columns:
        hist["id"] = hist["id"].astype(str)

    if "checked_at" in hist.columns:
        hist["checked_at"] = pd.to_datetime(hist["checked_at"], errors="coerce", utc=True)

    for col in ["play_count", "upvote_count", "comment_count"]:
        if col in hist.columns:
            hist[col] = to_number(hist[col])

    return hist


def add_growth_features(db, hist, window_hours):
    db = db.copy()

    for col in [
        "play_delta_window",
        "upvote_delta_window",
        "comment_delta_window",
    ]:
        db[col] = 0.0

    if hist.empty or "id" not in hist.columns or "checked_at" not in hist.columns:
        return db

    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(hours=window_hours)
    recent = hist[hist["checked_at"] >= cutoff].copy()

    if recent.empty:
        return db

    rows = []

    for song_id, g in recent.groupby("id"):
        g = g.sort_values("checked_at")

        if len(g) < 2:
            continue

        first = g.iloc[0]
        last = g.iloc[-1]

        rows.append({
            "id": str(song_id),
            "play_delta_window": max(0, float(last.get("play_count", 0)) - float(first.get("play_count", 0))),
            "upvote_delta_window": max(0, float(last.get("upvote_count", 0)) - float(first.get("upvote_count", 0))),
            "comment_delta_window": max(0, float(last.get("comment_count", 0)) - float(first.get("comment_count", 0))),
        })

    if not rows:
        return db

    growth = pd.DataFrame(rows)
    db = db.merge(growth, on="id", how="left", suffixes=("", "_growth"))

    for col in ["play_delta_window", "upvote_delta_window", "comment_delta_window"]:
        db[col] = db[col].fillna(0)

    return db


def filter_view(df):
    view = df.copy()

    if "created_at" in view.columns:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=MAX_AGE_DAYS)
        view = view[view["created_at"].isna() | (view["created_at"] >= cutoff)].copy()

    return view


def score_songs(db, hist):
    view = filter_view(db)
    now = pd.Timestamp.now(tz="UTC")

    if "created_at" not in view.columns:
        view["created_at"] = pd.NaT

    view["age_hours"] = (now - view["created_at"]).dt.total_seconds() / 3600
    view["age_hours"] = view["age_hours"].clip(lower=0)
    view["remaining_hours"] = (RETENTION_HOURS - view["age_hours"]).clip(lower=0)
    view["freshness"] = (view["remaining_hours"] / RETENTION_HOURS).clip(lower=0, upper=1)
    view["freshness_score"] = (view["freshness"] ** FRESHNESS_POWER) * FRESHNESS_WEIGHT

    view = add_growth_features(view, hist, GROWTH_WINDOW_HOURS)

    for col in ["play_count", "upvote_count", "comment_count"]:
        if col not in view.columns:
            view[col] = 0
        view[col] = to_number(view[col])

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
        PLAY_WEIGHT * view["play_count"].apply(lambda x: math.log1p(max(0, x)))
        + LIKE_WEIGHT * view["upvote_count"].apply(lambda x: math.log1p(max(0, x)))
        + COMMENT_WEIGHT * view["effective_comment_count"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score_raw"] = (
        0.4 * view["play_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 2.0 * view["upvote_delta_window"].apply(lambda x: math.log1p(max(0, x)))
        + 3.0 * view["comment_delta_window"].apply(lambda x: math.log1p(max(0, x)))
    )

    view["growth_score"] = view["growth_score_raw"] * GROWTH_WEIGHT
    view["trend_score"] = view["base_score"] + view["growth_score"] + view["freshness_score"]

    ranked = view.sort_values("trend_score", ascending=False, na_position="last").head(TOP_N).copy()
    ranked = ranked.reset_index(drop=True)
    ranked["new_current_rank"] = range(1, len(ranked) + 1)

    return ranked[[
        "id", "new_current_rank",
        "trend_score", "base_score", "growth_score", "freshness_score",
        "play_count", "upvote_count", "comment_count", "effective_comment_count",
    ]]


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

        old_current = dict(
            zip(
                old_rank_df["id"].astype(str),
                old_rank_df["current_rank"],
            )
        )

    ranked = score_songs(db, hist)

    ranked["previous_rank_new"] = ranked["id"].map(old_current)
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
            "previous_rank",
            "current_rank",
            "rank_change",
            "rank_status",
            "current_score",
            "base_score",
            "growth_score",
            "freshness_score",
        ],
        errors="ignore",
    )

    db = db.merge(
        ranked.rename(
            columns={
                "new_current_rank": "current_rank",
                "previous_rank_new": "previous_rank",
                "rank_change_new": "rank_change",
                "rank_status_new": "rank_status",
                "current_score_new": "current_score",
                "base_score_new": "base_score",
                "growth_score_new": "growth_score",
                "freshness_score_new": "freshness_score",
            }
        )[[
            "id",
            "current_rank", "previous_rank", "rank_change", "rank_status",
            "current_score", "base_score", "growth_score", "freshness_score",
            "peak_play_count_new", "peak_upvote_count_new",
            "peak_comment_count_new", "peak_adjusted_comment_count_new",
        ]],
        on="id",
        how="left",
    )

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

    check = pd.read_csv(DB_PATH)
    print(f"[rank_movement] saved db_rows={len(check)} -> {DB_PATH}")
    print(f"[rank_movement] ranked_rows={len(ranked)}")

    moved = ranked[ranked["rank_change_new"].notna() & (ranked["rank_change_new"] != 0)]
    print(f"[rank_movement] moved_rows={len(moved)}")


if __name__ == "__main__":
    main()
