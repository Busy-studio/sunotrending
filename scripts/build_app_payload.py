import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from ranking_core import (
    PLAY_WEIGHT, LIKE_WEIGHT, COMMENT_WEIGHT, GROWTH_WEIGHT, FRESHNESS_WEIGHT,
    FRESHNESS_POWER, GROWTH_WINDOW_HOURS, MAX_AGE_DAYS,
    add_outlier_flags, filter_active, prepare_db, prepare_history, score_songs,
)

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "suno_song_db.csv"
HISTORY_PATH = DATA_DIR / "suno_song_history.csv"
PAYLOAD_PATH = DATA_DIR / "suno_app_payload.json"
CONFIG_PATH = Path("config/rain_crew.json")

TOP_N = int(os.getenv("APP_PAYLOAD_TOP_N", "200"))
NEW_SONGS_LIMIT = int(os.getenv("APP_PAYLOAD_NEW_SONGS_LIMIT", "300"))
RAIN_CREW_LIMIT = int(os.getenv("APP_PAYLOAD_RAIN_CREW_LIMIT", "300"))
HISTORY_POINTS_PER_SONG = int(os.getenv("APP_PAYLOAD_HISTORY_POINTS", "80"))
OUTLIER_SIGMA = float(os.getenv("OUTLIER_SIGMA", "6.0"))
OUTLIER_USE_LOG = os.getenv("OUTLIER_USE_LOG", "true").lower() in {"1", "true", "yes", "y"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    s = str(value).strip()
    if s.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return s


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        s = str(value).strip()
        if s.lower() in {"", "nan", "none", "null", "<na>", "-"}:
            return default
        return float(s)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    return int(safe_float(value, default))


def iso_or_blank(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(ts):
            return ""
        return ts.isoformat()
    except Exception:
        return ""


def display_time(value: Any) -> str:
    try:
        if pd.isna(value):
            return "-"
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(ts):
            return "-"
        return ts.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "-"


def normalize_handle(value: Any) -> str:
    handle = clean_text(value)
    if handle.startswith("@"):
        handle = handle[1:]
    return handle


def creator_display(row: pd.Series) -> tuple[str, str]:
    display_name = clean_text(row.get("display_name", ""))
    handle = normalize_handle(row.get("handle", ""))
    return display_name or handle or "-", f"@{handle}" if handle else ""


def is_fake_rsc_token(value: Any) -> bool:
    s = clean_text(value)
    return not s or (s.startswith("$") and len(s) <= 8)


def lyrics_bundle(row: pd.Series) -> str:
    parts = []
    for col in ["lyrics", "prompt", "gpt_description_prompt"]:
        if col in row.index and not is_fake_rsc_token(row.get(col, "")):
            txt = clean_text(row.get(col, ""))
            if txt:
                parts.append(txt)
    return "\n\n".join(parts)


def build_song_payload(df: pd.DataFrame) -> list[dict[str, Any]]:
    songs = []
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        creator, handle = creator_display(row)
        rank = safe_int(row.get("rank", idx), idx)
        song_id = clean_text(row.get("id", ""))
        song_url = clean_text(row.get("song_url", "")) or (f"https://suno.com/song/{song_id}" if song_id else "")

        songs.append({
            "rank": rank,
            "rank_change": safe_float(row.get("rank_change", None), None),
            "rank_status": clean_text(row.get("rank_status", "")),
            "previous_rank": safe_float(row.get("previous_rank", None), None),
            "current_rank_saved": safe_float(row.get("current_rank", None), None),
            "id": song_id,
            "title": clean_text(row.get("title", "Untitled")) or "Untitled",
            "creator": creator,
            "handle": handle,
            "user_id": clean_text(row.get("user_id", "")),
            "created_at": display_time(row.get("created_at", None)),
            "created_at_raw": iso_or_blank(row.get("created_at", None)),
            "style_tags": clean_text(row.get("display_tags", "")),
            "play_count": safe_int(row.get("play_count", 0)),
            "upvote_count": safe_int(row.get("upvote_count", 0)),
            "comment_count": safe_int(row.get("comment_count", 0)),
            "effective_comment_count": safe_float(row.get("effective_comment_count", row.get("comment_count", 0))),
            "adjusted_comment_count": safe_float(row.get("adjusted_comment_count", row.get("comment_count", 0))),
            "comment_quality_ratio": safe_float(row.get("comment_quality_ratio", 1), 1),
            "is_outlier": bool(row.get("is_outlier", False)) if not pd.isna(row.get("is_outlier", False)) else False,
            "outlier_reasons": clean_text(row.get("outlier_reasons", "")),
            "song_url": song_url,
            "audio_url": clean_text(row.get("audio_url", "")),
            "image_url": clean_text(row.get("image_url", "")),
            "lyrics": lyrics_bundle(row),
            "trend_score": safe_float(row.get("trend_score", row.get("current_score", 0))),
            "base_score": safe_float(row.get("base_score", 0)),
            "growth_score": safe_float(row.get("growth_score", 0)),
            "freshness_score": safe_float(row.get("freshness_score", 0)),
            "growth_score_raw": safe_float(row.get("growth_score_raw", 0)),
            "play_delta_window": safe_float(row.get("play_delta_window", 0)),
            "upvote_delta_window": safe_float(row.get("upvote_delta_window", 0)),
            "comment_delta_window": safe_float(row.get("comment_delta_window", 0)),
            "freshness": safe_float(row.get("freshness", 0)),
            "age_hours": safe_float(row.get("age_hours", 0)),
        })
    return songs


def build_history_payload(hist: pd.DataFrame, song_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if hist is None or hist.empty or "id" not in hist.columns or "checked_at" not in hist.columns:
        return {}

    h = prepare_history(hist)
    song_id_set = {str(x) for x in song_ids if str(x)}
    h = h[h["id"].astype(str).isin(song_id_set)].copy()
    if h.empty:
        return {}

    h = h.sort_values("checked_at")
    result = {}
    for song_id, g in h.groupby("id"):
        rows = []
        for _, row in g.tail(HISTORY_POINTS_PER_SONG).iterrows():
            checked_at = row.get("checked_at")
            checked_txt = checked_at.strftime("%m-%d %H:%M") if pd.notna(checked_at) else "-"
            rows.append({
                "checked_at": checked_txt,
                "play_count": safe_int(row.get("play_count", 0)),
                "upvote_count": safe_int(row.get("upvote_count", 0)),
                "comment_count": safe_int(row.get("comment_count", 0)),
            })
        result[str(song_id)] = rows
    return result


def load_rain_crew_config() -> dict[str, set[str]]:
    empty = {"handles": set(), "user_ids": set(), "display_names": set()}
    if not CONFIG_PATH.exists():
        return empty

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    return {
        "handles": {normalize_handle(x).lower() for x in raw.get("handles", []) if normalize_handle(x)},
        "user_ids": {clean_text(x).lower() for x in raw.get("user_ids", []) if clean_text(x)},
        "display_names": {clean_text(x).lower() for x in raw.get("display_names", []) if clean_text(x)},
    }


def filter_rain_crew(df: pd.DataFrame) -> pd.DataFrame:
    config = load_rain_crew_config()
    if not any(config.values()):
        return df.iloc[0:0].copy()

    handles = df["handle"].apply(normalize_handle).str.lower() if "handle" in df.columns else pd.Series([""] * len(df), index=df.index)
    user_ids = df["user_id"].astype(str).str.strip().str.lower() if "user_id" in df.columns else pd.Series([""] * len(df), index=df.index)
    display_names = df["display_name"].astype(str).str.strip().str.lower() if "display_name" in df.columns else pd.Series([""] * len(df), index=df.index)

    mask = handles.isin(config["handles"]) | user_ids.isin(config["user_ids"]) | display_names.isin(config["display_names"])
    return df[mask].copy()


def with_rank(df: pd.DataFrame, start: int = 1) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    if "rank" in df.columns:
        df = df.drop(columns=["rank"])
    df.insert(0, "rank", range(start, start + len(df)))
    return df


def make_tab(df: pd.DataFrame, hist: pd.DataFrame, description: str) -> dict[str, Any]:
    songs = build_song_payload(df)
    return {
        "description": description,
        "count": len(songs),
        "songs": songs,
        "histories": build_history_payload(hist, [s["id"] for s in songs]),
    }


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Missing {DB_PATH}")

    db = pd.read_csv(DB_PATH)
    hist = pd.read_csv(HISTORY_PATH) if HISTORY_PATH.exists() else pd.DataFrame()

    db = prepare_db(db)
    hist = prepare_history(hist)

    scored = score_songs(db, hist)
    active = filter_active(scored, max_age_days=MAX_AGE_DAYS)
    active = add_outlier_flags(active, sigma=OUTLIER_SIGMA, use_log=OUTLIER_USE_LOG)

    new_songs_df = with_rank(
        active.sort_values("created_at", ascending=False, na_position="last").head(NEW_SONGS_LIMIT)
    )
    top200_df = with_rank(
        active.sort_values("trend_score", ascending=False, na_position="last").head(TOP_N)
    )
    rain_crew_df = with_rank(
        filter_rain_crew(active).sort_values("created_at", ascending=False, na_position="last").head(RAIN_CREW_LIMIT)
    )

    newest_created = db["created_at"].max() if "created_at" in db.columns else pd.NaT
    last_checked = db["last_checked_at"].max() if "last_checked_at" in db.columns else pd.NaT

    payload = {
        "version": 1,
        "meta": {
            "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "active_song_count": int(len(active)),
            "db_song_count": int(len(db)),
            "history_row_count": int(len(hist)),
            "newest_created_at": display_time(newest_created),
            "last_checked_at": display_time(last_checked),
            "max_age_days": MAX_AGE_DAYS,
            "top_n": TOP_N,
            "ranking": {
                "play_weight": PLAY_WEIGHT,
                "like_weight": LIKE_WEIGHT,
                "comment_weight": COMMENT_WEIGHT,
                "growth_weight": GROWTH_WEIGHT,
                "freshness_weight": FRESHNESS_WEIGHT,
                "freshness_power": FRESHNESS_POWER,
                "growth_window_hours": GROWTH_WINDOW_HOURS,
            },
        },
        "tabs": {
            "new_songs": make_tab(new_songs_df, hist, "생성일 기준 최신순"),
            "top200": make_tab(top200_df, hist, "최근 4일 이내 곡 중 trend_score 상위 200"),
            "rain_crew": make_tab(rain_crew_df, hist, "Rain Crew 설정에 포함된 크리에이터 곡 최신순"),
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with PAYLOAD_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[app_payload] saved {PAYLOAD_PATH}")
    print(f"[app_payload] new_songs={len(new_songs_df)} top200={len(top200_df)} rain_crew={len(rain_crew_df)}")


if __name__ == "__main__":
    main()
