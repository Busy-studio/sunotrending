import math
import os
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

RETENTION_HOURS = int(os.getenv("SONG_RETENTION_HOURS", "96"))
MAX_AGE_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))
GROWTH_WINDOW_HOURS = int(os.getenv("GROWTH_WINDOW_HOURS", "3"))

PLAY_WEIGHT = float(os.getenv("PLAY_WEIGHT", "1.0"))
LIKE_WEIGHT = float(os.getenv("LIKE_WEIGHT", "3.0"))
COMMENT_WEIGHT = float(os.getenv("COMMENT_WEIGHT", "4.0"))
GROWTH_WEIGHT = float(os.getenv("GROWTH_WEIGHT", "1.5"))
FRESHNESS_WEIGHT = float(os.getenv("FRESHNESS_WEIGHT", "35.0"))
FRESHNESS_POWER = float(os.getenv("FRESHNESS_POWER", "1.35"))


def to_number(series, default=0):
    return pd.to_numeric(series, errors="coerce").fillna(default)


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """Parse a datetime Series robustly even when string formats are mixed."""
    if is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce", utc=True)
    # Fast path for consistent strings; scalar fallback fixes mixed fractional/non-fractional strings.
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    missing = parsed.isna() & series.notna() & ~series.astype(str).str.strip().str.lower().isin(["", "nan", "none", "null", "<na>", "nat"])
    if bool(missing.any()):
        parsed.loc[missing] = series.loc[missing].apply(lambda x: pd.to_datetime(x, errors="coerce", utc=True))
    return parsed


def prepare_db(db: pd.DataFrame) -> pd.DataFrame:
    db = db.copy()

    if "id" in db.columns:
        db["id"] = db["id"].astype(str)

    for col in ["created_at", "first_seen_at", "last_checked_at", "comment_quality_checked_at"]:
        if col in db.columns:
            db[col] = parse_datetime_series(db[col])

    numeric_cols = [
        "play_count", "upvote_count", "comment_count", "flag_count",
        "adjusted_comment_count", "comment_quality_ratio", "analyzed_comment_count",
        "meaningful_count", "generic_count", "mention_only_count", "emoji_only_count",
        "previous_rank", "current_rank", "rank_change",
        "current_score", "base_score", "growth_score", "freshness_score",
        "best_rank", "best_trend_score", "peak_play_count", "peak_upvote_count",
        "peak_comment_count", "peak_adjusted_comment_count",
    ]

    for col in numeric_cols:
        if col in db.columns:
            db[col] = pd.to_numeric(db[col], errors="coerce")

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col not in db.columns:
            db[col] = 0
        db[col] = db[col].fillna(0)

    if "adjusted_comment_count" in db.columns:
        db["adjusted_comment_count"] = db["adjusted_comment_count"].fillna(db["comment_count"])
    else:
        db["adjusted_comment_count"] = db["comment_count"]

    if "comment_quality_ratio" in db.columns:
        db["comment_quality_ratio"] = db["comment_quality_ratio"].fillna(1)
    else:
        db["comment_quality_ratio"] = 1

    if "song_url" not in db.columns and "id" in db.columns:
        db["song_url"] = "https://suno.com/song/" + db["id"].astype(str)

    return db


def prepare_history(hist: pd.DataFrame | None) -> pd.DataFrame:
    if hist is None or hist.empty:
        return pd.DataFrame()

    hist = hist.copy()

    if "id" in hist.columns:
        hist["id"] = hist["id"].astype(str)

    for col in ["checked_at", "created_at"]:
        if col in hist.columns:
            hist[col] = parse_datetime_series(hist[col])

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col in hist.columns:
            hist[col] = to_number(hist[col])
        else:
            hist[col] = 0

    return hist



def restore_created_at_from_history(db: pd.DataFrame, hist: pd.DataFrame | None) -> pd.DataFrame:
    """Fill missing DB created_at values from history snapshots.

    This must run before scoring, rank movement, and archive pruning.
    Some rows can temporarily lose created_at in the active DB while history still
    preserves it; without this restore, Top 200 payload and saved DB ranks drift.
    """
    if db is None or db.empty:
        return db

    if hist is None or hist.empty:
        return db.copy()

    if "id" not in db.columns or "id" not in hist.columns or "created_at" not in hist.columns:
        return db.copy()

    out = db.copy()
    hist = hist.copy()

    if "created_at" not in out.columns:
        out["created_at"] = pd.NaT

    out["id"] = out["id"].astype(str)
    hist["id"] = hist["id"].astype(str)

    db_created = parse_datetime_series(out["created_at"])
    hist_created = parse_datetime_series(hist["created_at"])
    hist = hist.assign(__created_at_dt=hist_created).dropna(subset=["__created_at_dt"])

    if hist.empty:
        return out

    # Original created_at should be stable. Use the earliest valid value seen.
    created_map = hist.groupby("id")["__created_at_dt"].min()
    missing = db_created.isna()
    restored = out.loc[missing, "id"].map(created_map)
    has_restored = restored.notna()

    if bool(has_restored.any()):
        restored_values = restored[has_restored].dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
        out.loc[missing & has_restored, "created_at"] = restored_values

    return out


def prepare_rankable_db(db: pd.DataFrame, hist: pd.DataFrame | None = None) -> pd.DataFrame:
    """Prepare DB for every rank/archive/payload calculation using one rule set."""
    prepared = prepare_db(db)
    prepared = restore_created_at_from_history(prepared, hist)
    return prepare_db(prepared)


def serialize_datetime_columns_for_csv(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Serialize datetime columns consistently before writing CSV.

    Mixed timestamp strings like ``2026-05-11 16:03:56+00:00`` and
    ``2026-05-11 16:03:56.123000+00:00`` can make pandas parse a few rows as
    NaT on the next read. Always write UTC timestamps with microseconds.
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    if columns is None:
        columns = ["created_at", "first_seen_at", "last_checked_at", "comment_quality_checked_at", "best_score_at"]

    for col in columns:
        if col not in out.columns:
            continue
        # Use scalar parsing to handle mixed ISO strings with/without fractional seconds.
        parsed = parse_datetime_series(out[col])
        valid = parsed.notna()
        if not bool(valid.any()):
            continue
        formatted = parsed[valid].dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
        out[col] = out[col].astype("object")
        out.loc[valid, col] = formatted

    return out

def add_growth_features(db: pd.DataFrame, hist: pd.DataFrame, window_hours: int = GROWTH_WINDOW_HOURS) -> pd.DataFrame:
    db = db.copy()

    for col in [
        "play_delta_window", "upvote_delta_window", "comment_delta_window",
        "play_velocity_per_hour", "upvote_velocity_per_hour", "comment_velocity_per_hour",
    ]:
        db[col] = 0.0

    if hist is None or hist.empty or "id" not in hist.columns or "checked_at" not in hist.columns:
        return db

    if "id" not in db.columns:
        return db

    hist = prepare_history(hist)

    db_created = db[["id", "created_at"]].copy() if "created_at" in db.columns else db[["id"]].copy()
    if "created_at" not in db_created.columns:
        db_created["created_at"] = pd.NaT
    db_created["id"] = db_created["id"].astype(str)
    db_created = db_created.rename(columns={"created_at": "song_created_at"})
    db_created["song_created_at"] = parse_datetime_series(db_created["song_created_at"])

    hist = hist.merge(db_created, on="id", how="left")
    rows = []

    for song_id, g in hist.groupby("id"):
        g = g.sort_values("checked_at").copy()
        if g.empty:
            continue

        created_at = g["song_created_at"].dropna()
        if created_at.empty:
            continue

        anchor_time = created_at.iloc[0] + pd.Timedelta(hours=window_hours)
        after_anchor = g[g["checked_at"] >= anchor_time].copy()

        if len(after_anchor) < 2:
            continue

        first = after_anchor.iloc[0]
        last = after_anchor.iloc[-1]
        hours = (last["checked_at"] - first["checked_at"]).total_seconds() / 3600

        if hours <= 0:
            continue

        play_delta_total = max(0, float(last.get("play_count", 0)) - float(first.get("play_count", 0)))
        upvote_delta_total = max(0, float(last.get("upvote_count", 0)) - float(first.get("upvote_count", 0)))
        comment_delta_total = max(0, float(last.get("comment_count", 0)) - float(first.get("comment_count", 0)))

        play_velocity = play_delta_total / hours
        upvote_velocity = upvote_delta_total / hours
        comment_velocity = comment_delta_total / hours

        rows.append({
            "id": str(song_id),
            "play_delta_window": play_velocity * window_hours,
            "upvote_delta_window": upvote_velocity * window_hours,
            "comment_delta_window": comment_velocity * window_hours,
            "play_velocity_per_hour": play_velocity,
            "upvote_velocity_per_hour": upvote_velocity,
            "comment_velocity_per_hour": comment_velocity,
        })

    if not rows:
        return db

    growth = pd.DataFrame(rows)
    db = db.merge(growth, on="id", how="left", suffixes=("", "_growth"))

    for col in [
        "play_delta_window", "upvote_delta_window", "comment_delta_window",
        "play_velocity_per_hour", "upvote_velocity_per_hour", "comment_velocity_per_hour",
    ]:
        growth_col = f"{col}_growth"
        if growth_col in db.columns:
            db[col] = db[growth_col].fillna(db[col])
            db = db.drop(columns=[growth_col], errors="ignore")
        db[col] = db[col].fillna(0)

    return db


def score_songs(
    db: pd.DataFrame,
    hist: pd.DataFrame,
    play_weight: float = PLAY_WEIGHT,
    like_weight: float = LIKE_WEIGHT,
    comment_weight: float = COMMENT_WEIGHT,
    growth_weight: float = GROWTH_WEIGHT,
    freshness_weight: float = FRESHNESS_WEIGHT,
    growth_window_hours: int = GROWTH_WINDOW_HOURS,
    freshness_power: float = FRESHNESS_POWER,
) -> pd.DataFrame:
    view = prepare_rankable_db(db, hist)
    now = pd.Timestamp.now(tz="UTC")

    if "created_at" not in view.columns:
        view["created_at"] = pd.NaT

    view["age_hours"] = (now - view["created_at"]).dt.total_seconds() / 3600
    view["age_hours"] = view["age_hours"].clip(lower=0)
    view["remaining_hours"] = (RETENTION_HOURS - view["age_hours"]).clip(lower=0)
    view["freshness"] = (view["remaining_hours"] / RETENTION_HOURS).clip(lower=0, upper=1)
    view["freshness_score"] = (view["freshness"] ** freshness_power) * freshness_weight

    view = add_growth_features(view, hist, growth_window_hours)

    for col in ["play_count", "upvote_count", "comment_count", "adjusted_comment_count"]:
        if col not in view.columns:
            view[col] = 0
        view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0)

    view["effective_comment_count"] = view["adjusted_comment_count"].fillna(view["comment_count"]).clip(lower=0)

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
    view["trend_score"] = view["base_score"] + view["growth_score"] + view["freshness_score"]

    return view


def filter_active(df: pd.DataFrame, max_age_days: int = MAX_AGE_DAYS, hide_contest: bool = False) -> pd.DataFrame:
    view = df.copy()

    if hide_contest:
        if "is_contest_clip" in view.columns:
            view = view[view["is_contest_clip"].astype(str).str.lower() != "true"]
        if "download_disabled_reason" in view.columns:
            view = view[view["download_disabled_reason"].astype(str) != "remix_contest"]
        if "contest_ids" in view.columns:
            contest_str = view["contest_ids"].astype(str).str.strip().str.lower()
            view = view[view["contest_ids"].isna() | contest_str.isin(["", "nan", "none"])]

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max_age_days)
    if "created_at" in view.columns:
        view = view[view["created_at"].isna() | (view["created_at"] >= cutoff)]

    return view.copy()


def add_outlier_flags(df: pd.DataFrame, sigma: float = 6.0, use_log: bool = True) -> pd.DataFrame:
    view = df.copy()
    metrics = {"play_count": "play", "upvote_count": "like", "comment_count": "comment"}

    view["is_outlier"] = False
    view["outlier_reasons"] = ""
    reason_lists = [[] for _ in range(len(view))]

    for col, label in metrics.items():
        if col not in view.columns:
            continue

        values = pd.to_numeric(view[col], errors="coerce").fillna(0)
        values_for_z = values.apply(lambda x: math.log1p(max(0, x))) if use_log else values
        std = values_for_z.std(ddof=0)

        if std == 0 or pd.isna(std):
            continue

        z = (values_for_z - values_for_z.mean()) / std
        flag = z >= sigma
        view[f"{label}_zscore"] = z
        view[f"{label}_outlier"] = flag

        for i, is_flagged in enumerate(flag.tolist()):
            if is_flagged:
                reason_lists[i].append(f"{label} {int(values.iloc[i]):,} / z={z.iloc[i]:.2f}")

    view["is_outlier"] = [len(x) > 0 for x in reason_lists]
    view["outlier_reasons"] = [" | ".join(x) for x in reason_lists]
    return view
