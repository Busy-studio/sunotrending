import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import ftfy
except Exception:
    ftfy = None

from ranking_core import (
    PLAY_WEIGHT, LIKE_WEIGHT, COMMENT_WEIGHT, GROWTH_WEIGHT, FRESHNESS_WEIGHT,
    FRESHNESS_POWER, GROWTH_WINDOW_HOURS, MAX_AGE_DAYS,
    add_outlier_flags, prepare_db, prepare_history, score_songs,
    restore_created_at_from_history as core_restore_created_at_from_history,
)

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "suno_song_db.csv"
HISTORY_PATH = DATA_DIR / "suno_song_history.csv"
PAYLOAD_PATH = DATA_DIR / "suno_app_payload.json"
CONFIG_PATH = Path("config/rain_crew.json")

TOP_N = int(os.getenv("APP_PAYLOAD_TOP_N", os.getenv("PAYLOAD_TOP200_LIMIT", "200")))
NEW_SONGS_LIMIT = int(os.getenv("APP_PAYLOAD_NEW_SONGS_LIMIT", os.getenv("PAYLOAD_NEW_SONGS_LIMIT", "300")))
RAIN_CREW_LIMIT = int(os.getenv("APP_PAYLOAD_RAIN_CREW_LIMIT", os.getenv("PAYLOAD_RAIN_CREW_LIMIT", "300")))
HISTORY_POINTS_PER_SONG = int(os.getenv("APP_PAYLOAD_HISTORY_POINTS", os.getenv("PAYLOAD_HISTORY_POINTS", "80")))
OUTLIER_SIGMA = float(os.getenv("OUTLIER_SIGMA", "6.0"))
OUTLIER_USE_LOG = os.getenv("OUTLIER_USE_LOG", "true").lower() in {"1", "true", "yes", "y"}

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


def dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.columns.duplicated().any():
        dupes = df.columns[df.columns.duplicated(keep=False)].tolist()
        print(f"[app_payload] duplicate columns found, keeping last values: {dupes}")
        return df.loc[:, ~df.columns.duplicated(keep="last")].copy()
    return df


def broken_score(s: str) -> int:
    if not s:
        return 999999
    bad_markers = [
        "Ã", "ã", "Â", "â", "ð", "Ð", "Ñ", "Î", "Ï",
        "Å", "¤", "¦", "§", "¨", "©", "ª", "«", "¬", "®", "¯", "°", "±", "²", "³",
    ]
    score = sum(s.count(ch) * 3 for ch in bad_markers)
    score += sum(5 for ch in s if 0x80 <= ord(ch) <= 0x9F)
    score += max(0, 8 - len(s))
    return score


def try_decode_utf8_from_latinish(s: str) -> list[str]:
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


def fix_mojibake(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

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
        for item in frontier:
            for fixed in try_decode_utf8_from_latinish(item):
                if fixed and fixed not in candidates:
                    candidates.append(fixed)
                    new_frontier.append(fixed)
            if ftfy is not None:
                try:
                    fixed = ftfy.fix_text(item)
                    if fixed and fixed not in candidates:
                        candidates.append(fixed)
                        new_frontier.append(fixed)
                except Exception:
                    pass
        frontier = new_frontier
        if not frontier:
            break

    return min(candidates, key=broken_score)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    s = fix_mojibake(value).strip()
    if s.lower() in {"", "nan", "none", "null", "<na>", "-"}:
        return ""
    return s


def safe_float(value: Any, default: float | None = 0.0) -> float | None:
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
    val = safe_float(value, default)
    if val is None:
        return default
    return int(val)


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
            "integrated_lufs": safe_float(row.get("integrated_lufs", None), None),
            "true_peak_db": safe_float(row.get("true_peak_db", None), None),
            "loudness_gain_db": safe_float(row.get("loudness_gain_db", None), None),
            "loudness_target_lufs": safe_float(row.get("loudness_target_lufs", -14.0), -14.0),
            "loudness_true_peak_ceiling_db": safe_float(row.get("loudness_true_peak_ceiling_db", -1.0), -1.0),
            "loudness_status": clean_text(row.get("loudness_status", "")),
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




def restore_created_at_from_history(db: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """Fill missing DB created_at values from history snapshots.

    Some rows can lose created_at in the active DB while history still preserves it.
    Top 200/New Song/☔rain crew must all use restored created_at before scoring/filtering.
    """
    if db is None or db.empty:
        return db

    if hist is None or hist.empty:
        print("[app_payload] restore_created_at skipped: empty history")
        return db

    if "id" not in db.columns or "id" not in hist.columns or "created_at" not in hist.columns:
        print("[app_payload] restore_created_at skipped: required columns missing")
        return db

    db = db.copy()
    hist = hist.copy()

    if "created_at" not in db.columns:
        db["created_at"] = pd.NaT

    db["id"] = db["id"].astype(str)
    hist["id"] = hist["id"].astype(str)

    db_created = pd.to_datetime(db["created_at"], errors="coerce", utc=True)
    before_valid = int(db_created.notna().sum())

    hist_created = pd.to_datetime(hist["created_at"], errors="coerce", utc=True)
    hist = hist.assign(__created_at_dt=hist_created).dropna(subset=["__created_at_dt"])

    if hist.empty:
        print("[app_payload] restore_created_at skipped: no valid history created_at")
        return db

    # The original creation time for a song should be stable; use the earliest valid value seen in history.
    created_map = hist.groupby("id")["__created_at_dt"].min()
    missing = db_created.isna()
    restored = db.loc[missing, "id"].map(created_map)
    has_restored = restored.notna()
    restored_count = int(has_restored.sum())

    if restored_count:
        restored_values = restored[has_restored].dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
        db.loc[missing & has_restored, "created_at"] = restored_values

    after_valid = int(pd.to_datetime(db["created_at"], errors="coerce", utc=True).notna().sum())
    print(
        f"[app_payload] restore_created_at_from_history: "
        f"valid_before={before_valid}/{len(db)} restored={restored_count} valid_after={after_valid}/{len(db)}"
    )

    return db

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


def with_rank(df: pd.DataFrame, start: int = 1, clear_movement: bool = False) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    df = df.drop(columns=["rank"], errors="ignore")
    df.insert(0, "rank", range(start, start + len(df)))

    # New Song / rain crew의 rank는 단순 리스트 번호다.
    # 기존 Top 200 movement가 섞이면 오해되므로 non-ranking 탭에서는 숨긴다.
    if clear_movement:
        for col in ["rank_change", "rank_status", "previous_rank", "current_rank"]:
            if col in df.columns:
                df[col] = pd.NA if col != "rank_status" else ""
    return df


def make_tab(df: pd.DataFrame, hist: pd.DataFrame, title: str, description: str) -> dict[str, Any]:
    songs = build_song_payload(df)
    return {
        "title": title,
        "description": description,
        "count": len(songs),
        "songs": songs,
        "histories": build_history_payload(hist, [s["id"] for s in songs]),
    }


def require_valid_created_at(df: pd.DataFrame) -> pd.DataFrame:
    """Top 200/New Song 후보군은 현재 시각 기준 4일 이내 생성곡만 사용한다."""
    if "created_at" not in df.columns:
        return df.iloc[0:0].copy()
    created = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    return df[created.notna()].copy()


def build_active_candidates(scored: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Return every DB song created within the last MAX_AGE_DAYS days.

    중요: Top 200은 New Song 일부에서 파생하지 않고, 이 active 전체를 후보군으로 삼는다.
    """
    view = require_valid_created_at(scored)
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(days=MAX_AGE_DAYS)
    active = view[view["created_at"] >= cutoff].copy()
    return active, cutoff


def print_candidate_debug(db: pd.DataFrame, active: pd.DataFrame, top200: pd.DataFrame, cutoff: pd.Timestamp) -> None:
    print(f"[app_payload] db_rows={len(db)}")
    print(f"[app_payload] created_at_valid={int(pd.to_datetime(db.get('created_at'), errors='coerce', utc=True).notna().sum()) if 'created_at' in db.columns else 0}/{len(db)}")
    print(f"[app_payload] cutoff_utc={cutoff.isoformat()}")
    print(f"[app_payload] active_4d_rows={len(active)}")
    print(f"[app_payload] top200_rows={len(top200)}")

    if active.empty:
        print("[app_payload] active candidate set is empty")
        return

    sample_cols = [
        "title", "handle", "created_at", "play_count", "upvote_count", "comment_count",
        "trend_score", "base_score", "growth_score", "freshness_score", "age_hours",
    ]
    sample_cols = [c for c in sample_cols if c in active.columns]

    print("[app_payload] top20_by_trend_score:")
    print(active.sort_values(["trend_score", "created_at"], ascending=[False, False], na_position="last")[sample_cols].head(20).to_string(index=False))

    top200_ids = set(top200["id"].astype(str)) if "id" in top200.columns else set()
    for metric in ["play_count", "upvote_count", "comment_count"]:
        if metric not in active.columns:
            continue
        metric_top = active.sort_values(metric, ascending=False, na_position="last").head(20).copy()
        metric_top["in_top200"] = metric_top["id"].astype(str).isin(top200_ids) if "id" in metric_top.columns else False
        cols = ["in_top200"] + sample_cols
        cols = [c for c in cols if c in metric_top.columns]
        print(f"[app_payload] top20_by_{metric}:")
        print(metric_top[cols].to_string(index=False))


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Missing {DB_PATH}")

    db = pd.read_csv(DB_PATH)
    hist = pd.read_csv(HISTORY_PATH) if HISTORY_PATH.exists() else pd.DataFrame()

    db = dedupe_columns(db)
    hist = dedupe_columns(hist) if not hist.empty else pd.DataFrame()

    # DB created_at 누락분은 history snapshot에서 먼저 복구한다.
    # 이 단계가 빠지면 5월 10일처럼 DB created_at만 빈 곡들이 Top 200 후보에서 사라질 수 있다.
    db = core_restore_created_at_from_history(db, hist)

    db = dedupe_columns(prepare_db(dedupe_columns(db)))
    hist = prepare_history(dedupe_columns(hist)) if not hist.empty else pd.DataFrame()

    # 1) 전체 DB를 먼저 점수화한다.
    scored = dedupe_columns(score_songs(db, hist))

    # 2) 현재 시각 기준 4일 이내 생성곡 전체를 Top 200 후보군으로 삼는다.
    active, cutoff = build_active_candidates(scored)
    active = add_outlier_flags(active, sigma=OUTLIER_SIGMA, use_log=OUTLIER_USE_LOG)

    # 3) 각 탭은 모두 active 전체에서 독립적으로 만든다. Top 200은 New Song에서 파생하지 않는다.
    new_songs_df = with_rank(
        active.sort_values("created_at", ascending=False, na_position="last").head(NEW_SONGS_LIMIT),
        clear_movement=True,
    )

    top200_df = with_rank(
        active.sort_values(["trend_score", "created_at"], ascending=[False, False], na_position="last").head(TOP_N),
        clear_movement=False,
    )

    rain_crew_df = with_rank(
        filter_rain_crew(active).sort_values("created_at", ascending=False, na_position="last").head(RAIN_CREW_LIMIT),
        clear_movement=True,
    )

    newest_created = db["created_at"].max() if "created_at" in db.columns else pd.NaT
    last_checked = db["last_checked_at"].max() if "last_checked_at" in db.columns else pd.NaT

    print_candidate_debug(db, active, top200_df, cutoff)

    payload = {
        "version": 2,
        "meta": {
            "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "candidate_rule": f"valid created_at >= generated_at - {MAX_AGE_DAYS} days",
            "top200_rule": "score every active 4-day DB song, sort by trend_score desc, then created_at desc, then take top N",
            "active_song_count": int(len(active)),
            "db_song_count": int(len(db)),
            "history_row_count": int(len(hist)),
            "newest_created_at": display_time(newest_created),
            "last_checked_at": display_time(last_checked),
            "cutoff_utc": cutoff.isoformat(),
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
        "tabs_order": ["new_songs", "top200", "rain_crew"],
        "tabs": {
            "new_songs": make_tab(new_songs_df, hist, TAB_LABELS["new_songs"], TAB_DESCRIPTIONS["new_songs"]),
            "top200": make_tab(top200_df, hist, TAB_LABELS["top200"], TAB_DESCRIPTIONS["top200"]),
            "rain_crew": make_tab(rain_crew_df, hist, TAB_LABELS["rain_crew"], TAB_DESCRIPTIONS["rain_crew"]),
        },
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with PAYLOAD_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[app_payload] saved {PAYLOAD_PATH}")
    print(f"[app_payload] new_songs={len(new_songs_df)} top200={len(top200_df)} rain_crew={len(rain_crew_df)}")


if __name__ == "__main__":
    main()
