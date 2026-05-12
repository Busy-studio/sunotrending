import os
import re
import time
import math
import json
import unicodedata
from datetime import datetime, timezone

import pandas as pd
from text_utils import normalize_text_columns
import requests

from ranking_core import filter_active, score_songs


DB_PATH = "data/suno_song_db.csv"
HISTORY_PATH = "data/suno_song_history.csv"
QUALITY_PATH = "data/suno_comment_quality.csv"

TOP_N = int(os.getenv("COMMENT_ANALYZE_TOP_N", "200"))
REQUEST_SLEEP_SECONDS = float(os.getenv("COMMENT_REQUEST_SLEEP_SECONDS", "0.4"))
COMMENT_MAX_PAGES = int(os.getenv("COMMENT_MAX_PAGES", "3"))
COMMENT_MAX_ITEMS_PER_SONG = int(os.getenv("COMMENT_MAX_ITEMS_PER_SONG", "120"))

RETENTION_HOURS = 96
MAX_AGE_DAYS = int(os.getenv("SONG_RETENTION_DAYS", "4"))

PLAY_WEIGHT = float(os.getenv("PLAY_WEIGHT", "1.0"))
LIKE_WEIGHT = float(os.getenv("LIKE_WEIGHT", "3.0"))
COMMENT_WEIGHT = float(os.getenv("COMMENT_WEIGHT", "4.0"))
GROWTH_WEIGHT = float(os.getenv("GROWTH_WEIGHT", "1.5"))
FRESHNESS_WEIGHT = float(os.getenv("FRESHNESS_WEIGHT", "35.0"))
FRESHNESS_POWER = float(os.getenv("FRESHNESS_POWER", "1.35"))
GROWTH_WINDOW_HOURS = int(os.getenv("GROWTH_WINDOW_HOURS", "3"))

COMMENTS_API_BASE = "https://studio-api-prod.suno.com/api/gen"


MUSIC_TERMS = {
    "song", "track", "beat", "beats", "vocal", "vocals", "voice", "mix", "mixing",
    "melody", "melodies", "lyrics", "lyric", "chorus", "hook", "drop", "bass",
    "drums", "guitar", "piano", "synth", "sound", "sounds", "production",
    "arrangement", "vibe", "energy", "genre", "style", "flow", "rhythm",
    "master", "mastering", "instrumental", "verse", "bridge", "intro", "outro",
}

POSITIVE_TERMS = {
    "good", "great", "amazing", "awesome", "nice", "cool", "love", "loved",
    "enjoy", "enjoyed", "beautiful", "fire", "banger", "excellent", "perfect",
    "favorite", "fav", "incredible", "wonderful", "fantastic", "dope",
}

GENERIC_SHORT = {
    "nice", "good", "cool", "fire", "wow", "great", "amazing", "awesome",
    "love", "liked", "dope", "banger", "first", "lol", "ok", "yes", "no",
}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_str(value):
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def to_number(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def ensure_data_files():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Missing DB CSV: {DB_PATH}")

    os.makedirs("data", exist_ok=True)


def load_db():
    db = pd.read_csv(DB_PATH)

    if "id" not in db.columns:
        raise RuntimeError("DB must contain id column")

    db["id"] = db["id"].astype(str)

    for col in ["play_count", "upvote_count", "comment_count", "flag_count"]:
        if col in db.columns:
            db[col] = to_number(db[col])
        else:
            db[col] = 0

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


def score_for_top200(db, hist):
    """Select comment-analysis targets with the shared ranking core.

    Keep this script aligned with payload, rank movement, and archive scoring.
    """
    scored = score_songs(db, hist)
    active = filter_active(scored, max_age_days=MAX_AGE_DAYS, hide_contest=True)
    return active.sort_values(
        ["trend_score", "created_at"],
        ascending=[False, False],
        na_position="last",
    ).head(TOP_N).copy()

def fetch_comments(song_id, order="most_liked"):
    all_items = []
    cursor = None
    total_count = None

    headers = {
        "accept": "application/json",
        "origin": "https://suno.com",
        "referer": "https://suno.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }

    for page in range(COMMENT_MAX_PAGES):
        params = {"order": order}

        if cursor:
            params["cursor"] = cursor

        url = f"{COMMENTS_API_BASE}/{song_id}/comments"

        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[comments FAIL] {song_id} page={page + 1}: {e}")
            break

        if total_count is None:
            total_count = data.get("total_count")

        results = data.get("results", []) or []
        all_items.extend(results)

        cursor = data.get("next_cursor")

        if not cursor or len(all_items) >= COMMENT_MAX_ITEMS_PER_SONG:
            break

        time.sleep(REQUEST_SLEEP_SECONDS)

    return {
        "total_count": int(total_count or len(all_items)),
        "comments": all_items[:COMMENT_MAX_ITEMS_PER_SONG],
    }


def flatten_comments(payload):
    rows = []

    for c in payload.get("comments", []) or []:
        content = safe_str(c.get("content"))

        if content:
            rows.append({
                "id": safe_str(c.get("id")),
                "content": content,
                "user_handle": safe_str(c.get("user_handle")),
                "user_display_name": safe_str(c.get("user_display_name")),
                "num_likes": int(c.get("num_likes") or 0),
                "num_replies": int(c.get("num_replies") or 0),
                "created_at": safe_str(c.get("created_at")),
                "is_reply": False,
                "user_mentions": c.get("user_mentions", []) or [],
            })

        for reply in c.get("replies", []) or []:
            reply_content = safe_str(reply.get("content"))

            if reply_content:
                rows.append({
                    "id": safe_str(reply.get("id")),
                    "content": reply_content,
                    "user_handle": safe_str(reply.get("user_handle")),
                    "user_display_name": safe_str(reply.get("user_display_name")),
                    "num_likes": int(reply.get("num_likes") or 0),
                    "num_replies": 0,
                    "created_at": safe_str(reply.get("created_at")),
                    "is_reply": True,
                    "user_mentions": reply.get("user_mentions", []) or [],
                })

    return rows


def normalize_text(text):
    text = safe_str(text).lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def token_list(text):
    return re.findall(r"[a-zA-Z0-9가-힣]+", text.lower())


def has_letters_or_digits(text):
    return any(ch.isalnum() for ch in text)


def emoji_or_symbol_only(text):
    text = safe_str(text)

    if not text:
        return True

    if has_letters_or_digits(text):
        return False

    meaningful_symbols = 0

    for ch in text:
        if ch.isspace():
            continue

        cat = unicodedata.category(ch)
        if cat.startswith("S") or cat.startswith("P"):
            meaningful_symbols += 1

    return meaningful_symbols > 0


def repeated_chars_or_emoji(text):
    compact = re.sub(r"\s+", "", safe_str(text))

    if len(compact) <= 1:
        return False

    unique_chars = set(compact)

    if len(unique_chars) <= 2 and len(compact) >= 4:
        return True

    return False


def mention_only_comment(comment):
    text = normalize_text(comment.get("content"))
    tokens = token_list(text)

    if not text:
        return True

    mentions = comment.get("user_mentions", []) or []
    mention_names = set()

    for m in mentions:
        handle = normalize_text(m.get("handle"))
        display = normalize_text(m.get("display_name"))

        if handle:
            mention_names.add(handle)
        if display:
            mention_names.add(display)

    if text in mention_names:
        return True

    if len(tokens) <= 2 and mentions:
        joined = " ".join(tokens)
        for name in mention_names:
            name_tokens = " ".join(token_list(name))
            if joined == name_tokens:
                return True

    if len(tokens) == 1:
        word = tokens[0]

        if word not in POSITIVE_TERMS and word not in MUSIC_TERMS and len(word) >= 3:
            return True

    return False


def classify_comment(comment):
    raw = safe_str(comment.get("content"))
    text = normalize_text(raw)
    tokens = token_list(text)
    token_count = len(tokens)

    if not text:
        return "empty", 0.0

    if emoji_or_symbol_only(text):
        return "emoji_only", 0.0

    if repeated_chars_or_emoji(text):
        return "repeated", 0.1

    if mention_only_comment(comment):
        return "mention_only", 0.0

    token_set = set(tokens)

    has_music = bool(token_set & MUSIC_TERMS)
    has_positive = bool(token_set & POSITIVE_TERMS)

    if token_count <= 2:
        if text in GENERIC_SHORT or has_positive:
            return "generic_short", 0.35
        return "too_short", 0.15

    if token_count <= 4 and has_positive and not has_music:
        return "generic_positive", 0.55

    if has_music and token_count >= 4:
        return "meaningful_music", 1.0

    if has_positive and token_count >= 5:
        return "meaningful_reaction", 0.85

    if token_count >= 8:
        return "meaningful_long", 0.75

    return "generic", 0.45


def analyze_comment_rows(comment_rows, original_comment_count):
    analyzed_count = len(comment_rows)

    if analyzed_count == 0:
        return {
            "analyzed_comment_count": 0,
            "meaningful_count": 0,
            "generic_count": 0,
            "mention_only_count": 0,
            "emoji_only_count": 0,
            "weighted_quality_sum": 0.0,
            "comment_quality_ratio": 1.0,
            "adjusted_comment_count": float(original_comment_count),
            "comment_quality_summary": "no_comments_returned",
        }

    counts = {
        "meaningful_count": 0,
        "generic_count": 0,
        "mention_only_count": 0,
        "emoji_only_count": 0,
    }

    weighted_sum = 0.0
    label_counts = {}

    for row in comment_rows:
        label, weight = classify_comment(row)
        weighted_sum += weight
        label_counts[label] = label_counts.get(label, 0) + 1

        if label.startswith("meaningful"):
            counts["meaningful_count"] += 1
        elif label in {"mention_only"}:
            counts["mention_only_count"] += 1
        elif label in {"emoji_only", "repeated"}:
            counts["emoji_only_count"] += 1
        else:
            counts["generic_count"] += 1

    quality_ratio = weighted_sum / analyzed_count
    quality_ratio = max(0.0, min(1.0, quality_ratio))

    adjusted_comment_count = float(original_comment_count) * quality_ratio

    summary = ", ".join(
        f"{k}:{v}" for k, v in sorted(label_counts.items(), key=lambda x: (-x[1], x[0]))
    )

    return {
        "analyzed_comment_count": analyzed_count,
        **counts,
        "weighted_quality_sum": round(weighted_sum, 4),
        "comment_quality_ratio": round(quality_ratio, 4),
        "adjusted_comment_count": round(adjusted_comment_count, 2),
        "comment_quality_summary": summary,
    }


def main():
    ensure_data_files()

    db = load_db()
    hist = load_history()

    print(f"[load] db_rows={len(db)}")
    print(f"[load] hist_rows={len(hist)}")

    top = score_for_top200(db, hist)

    print(f"[top] analyze_target_rows={len(top)}")

    existing_quality = pd.DataFrame()

    if os.path.exists(QUALITY_PATH):
        try:
            existing_quality = pd.read_csv(QUALITY_PATH)
            if "id" in existing_quality.columns:
                existing_quality["id"] = existing_quality["id"].astype(str)
            print(f"[load] existing_quality_rows={len(existing_quality)}")
        except Exception as e:
            print(f"[WARN] failed to read existing quality csv: {e}")
            existing_quality = pd.DataFrame()

    quality_rows = []

    for idx, row in top.iterrows():
        song_id = safe_str(row.get("id"))
        comment_count = int(float(row.get("comment_count", 0) or 0))

        if not song_id or song_id == "nan":
            continue

        if comment_count <= 0:
            result = {
                "id": song_id,
                "comment_count": 0,
                "api_total_count": 0,
                "analyzed_comment_count": 0,
                "meaningful_count": 0,
                "generic_count": 0,
                "mention_only_count": 0,
                "emoji_only_count": 0,
                "weighted_quality_sum": 0.0,
                "comment_quality_ratio": 1.0,
                "adjusted_comment_count": 0.0,
                "comment_quality_summary": "no_comments",
                "checked_at": utc_now_iso(),
            }
            quality_rows.append(result)
            continue

        payload = fetch_comments(song_id)
        comment_rows = flatten_comments(payload)

        analysis = analyze_comment_rows(comment_rows, comment_count)

        result = {
            "id": song_id,
            "comment_count": comment_count,
            "api_total_count": payload.get("total_count", len(comment_rows)),
            **analysis,
            "checked_at": utc_now_iso(),
        }

        quality_rows.append(result)

        print(
            f"[quality] {song_id} comments={comment_count} "
            f"analyzed={result['analyzed_comment_count']} "
            f"ratio={result['comment_quality_ratio']} "
            f"adjusted={result['adjusted_comment_count']} "
            f"summary={result['comment_quality_summary']}"
        )

        time.sleep(REQUEST_SLEEP_SECONDS)

    quality_new = pd.DataFrame(quality_rows)

    if not existing_quality.empty and "id" in existing_quality.columns:
        old_rest = existing_quality[~existing_quality["id"].isin(quality_new["id"])].copy()
        quality_final = pd.concat([quality_new, old_rest], ignore_index=True)
    else:
        quality_final = quality_new

    quality_final = normalize_text_columns(quality_final, columns=["title", "handle", "comment_quality_summary"])
    quality_final.to_csv(QUALITY_PATH, index=False, encoding="utf-8-sig")

    check_quality = pd.read_csv(QUALITY_PATH)
    print(f"[save] quality_rows={len(check_quality)} -> {QUALITY_PATH}")

    if not quality_new.empty:
        merge_cols = [
            "id",
            "adjusted_comment_count",
            "comment_quality_ratio",
            "analyzed_comment_count",
            "meaningful_count",
            "generic_count",
            "mention_only_count",
            "emoji_only_count",
            "comment_quality_summary",
            "checked_at",
        ]

        update_quality = quality_new[merge_cols].copy()

        rename_map = {
            "checked_at": "comment_quality_checked_at",
        }
        update_quality = update_quality.rename(columns=rename_map)

        db = db.drop(
            columns=[
                "adjusted_comment_count",
                "comment_quality_ratio",
                "analyzed_comment_count",
                "meaningful_count",
                "generic_count",
                "mention_only_count",
                "emoji_only_count",
                "comment_quality_summary",
                "comment_quality_checked_at",
            ],
            errors="ignore",
        )

        db = db.merge(update_quality, on="id", how="left")

        db = normalize_text_columns(db)
        db.to_csv(DB_PATH, index=False, encoding="utf-8-sig")

        check_db = pd.read_csv(DB_PATH)
        print(f"[save] db_rows_with_quality={len(check_db)} -> {DB_PATH}")

    print("[done] comment quality analysis complete")


if __name__ == "__main__":
    main()
