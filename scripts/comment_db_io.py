"""Supabase-backed incremental Suno comment storage and quality summaries.

Design:
- Store raw comments once in public.suno_comments.
- New comments are inserted with analyzed_at = null.
- Quality analysis only classifies unanalyzed comments.
- Song-level quality summaries are recalculated from stored labels/weights, not by re-reading content.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from supabase import create_client


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_str(value) -> str:
    if value is None:
        return ""
    try:
        # pandas NA compatibility without importing pandas here.
        if value != value:
            return ""
    except Exception:
        pass
    return str(value).strip()


def get_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return None
    return create_client(url, key)


def stable_comment_id(song_id: str, content: str, created_at: str = "", user_handle: str = "") -> str:
    base = "|".join([safe_str(song_id), safe_str(created_at), safe_str(user_handle), safe_str(content)])
    return "generated_" + hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()


def normalize_comment_row(song_id: str, comment: dict, fetched_at: Optional[str] = None) -> dict:
    fetched_at = fetched_at or utc_now_iso()
    content = safe_str(comment.get("content"))
    comment_id = safe_str(comment.get("id")) or stable_comment_id(
        song_id=song_id,
        content=content,
        created_at=safe_str(comment.get("created_at")),
        user_handle=safe_str(comment.get("user_handle")),
    )

    mentions = comment.get("user_mentions", []) or []
    try:
        mentions_json = json.dumps(mentions, ensure_ascii=False)
    except Exception:
        mentions_json = "[]"

    return {
        "comment_id": comment_id,
        "song_id": safe_str(song_id),
        "content": content,
        "user_id": safe_str(comment.get("user_id")),
        "user_handle": safe_str(comment.get("user_handle")),
        "user_display_name": safe_str(comment.get("user_display_name")),
        "num_likes": safe_str(comment.get("num_likes", "0")),
        "num_replies": safe_str(comment.get("num_replies", "0")),
        "created_at": safe_str(comment.get("created_at")),
        "fetched_at": fetched_at,
        "is_reply": "true" if bool(comment.get("is_reply")) else "false",
        "parent_comment_id": safe_str(comment.get("parent_comment_id")),
        "user_mentions_json": mentions_json,
        "quality_label": safe_str(comment.get("quality_label")),
        "quality_weight": safe_str(comment.get("quality_weight")),
        "is_meaningful": safe_str(comment.get("is_meaningful")),
        "is_generic": safe_str(comment.get("is_generic")),
        "is_mention_only": safe_str(comment.get("is_mention_only")),
        "is_emoji_only": safe_str(comment.get("is_emoji_only")),
        "analyzed_at": safe_str(comment.get("analyzed_at")),
    }


def fetch_existing_comment_ids(sb, song_id: str, page_size: int = 1000) -> set:
    ids = set()
    start = 0
    while True:
        end = start + page_size - 1
        result = (
            sb.table("suno_comments")
            .select("comment_id")
            .eq("song_id", song_id)
            .range(start, end)
            .execute()
        )
        batch = result.data or []
        for row in batch:
            cid = safe_str(row.get("comment_id"))
            if cid:
                ids.add(cid)
        if len(batch) < page_size:
            break
        start += page_size
    return ids


def count_song_comments(sb, song_id: str) -> int:
    try:
        result = (
            sb.table("suno_comments")
            .select("comment_id", count="exact")
            .eq("song_id", song_id)
            .execute()
        )
        return int(result.count or 0)
    except Exception:
        return 0


def upsert_comments(sb, song_id: str, comment_rows: List[dict], chunk_size: int = 300) -> int:
    if not sb or not song_id or not comment_rows:
        return 0

    existing_ids = fetch_existing_comment_ids(sb, song_id)
    fetched_at = utc_now_iso()
    rows = []
    for raw in comment_rows:
        row = normalize_comment_row(song_id, raw, fetched_at=fetched_at)
        if not row["content"]:
            continue
        if row["comment_id"] in existing_ids:
            # Preserve previous analysis fields by not rewriting existing comments.
            continue
        rows.append(row)

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        if chunk:
            sb.table("suno_comments").upsert(chunk, on_conflict="comment_id").execute()
    return len(rows)


def fetch_unanalyzed_comments(sb, song_ids: Optional[Iterable[str]] = None, limit: int = 2000) -> List[dict]:
    query = (
        sb.table("suno_comments")
        .select("*")
        .is_("analyzed_at", "null")
        .limit(limit)
    )
    ids = [safe_str(x) for x in (song_ids or []) if safe_str(x)]
    if ids:
        # supabase-py supports in_ for PostgREST IN filters.
        query = query.in_("song_id", ids)
    result = query.execute()
    return result.data or []


def mark_comments_analyzed(sb, analyzed_rows: List[dict], chunk_size: int = 300) -> int:
    if not analyzed_rows:
        return 0
    analyzed_at = utc_now_iso()
    count = 0
    for row in analyzed_rows:
        cid = safe_str(row.get("comment_id"))
        if not cid:
            continue
        update = {
            "quality_label": safe_str(row.get("quality_label")),
            "quality_weight": safe_str(row.get("quality_weight", "0")),
            "is_meaningful": safe_str(row.get("is_meaningful")),
            "is_generic": safe_str(row.get("is_generic")),
            "is_mention_only": safe_str(row.get("is_mention_only")),
            "is_emoji_only": safe_str(row.get("is_emoji_only")),
            "analyzed_at": analyzed_at,
        }
        sb.table("suno_comments").update(update).eq("comment_id", cid).execute()
        count += 1
    return count


def fetch_analyzed_comments_for_song(sb, song_id: str, page_size: int = 1000) -> List[dict]:
    rows: List[dict] = []
    start = 0
    while True:
        end = start + page_size - 1
        result = (
            sb.table("suno_comments")
            .select("comment_id, quality_label, quality_weight, analyzed_at")
            .eq("song_id", song_id)
            .range(start, end)
            .execute()
        )
        batch = result.data or []
        rows.extend([r for r in batch if safe_str(r.get("analyzed_at"))])
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def summarize_song_quality(sb, song_id: str, original_comment_count: int) -> Dict[str, object]:
    rows = fetch_analyzed_comments_for_song(sb, song_id)
    analyzed_count = len(rows)
    if analyzed_count == 0:
        return {
            "analyzed_comment_count": 0,
            "meaningful_count": 0,
            "generic_count": 0,
            "mention_only_count": 0,
            "emoji_only_count": 0,
            "weighted_quality_sum": 0.0,
            "comment_quality_ratio": 1.0 if original_comment_count <= 0 else 0.0,
            "adjusted_comment_count": float(original_comment_count if original_comment_count <= 0 else 0),
            "comment_quality_summary": "no_analyzed_comments",
        }

    counts = {
        "meaningful_count": 0,
        "generic_count": 0,
        "mention_only_count": 0,
        "emoji_only_count": 0,
    }
    label_counts: Dict[str, int] = {}
    weighted_sum = 0.0

    for row in rows:
        label = safe_str(row.get("quality_label")) or "unknown"
        try:
            weight = float(row.get("quality_weight") or 0)
        except Exception:
            weight = 0.0
        weighted_sum += weight
        label_counts[label] = label_counts.get(label, 0) + 1

        if label.startswith("meaningful"):
            counts["meaningful_count"] += 1
        elif label == "mention_only":
            counts["mention_only_count"] += 1
        elif label in {"emoji_only", "repeated"}:
            counts["emoji_only_count"] += 1
        else:
            counts["generic_count"] += 1

    quality_ratio = max(0.0, min(1.0, weighted_sum / max(analyzed_count, 1)))
    adjusted_comment_count = float(original_comment_count) * quality_ratio
    summary = ", ".join(f"{k}:{v}" for k, v in sorted(label_counts.items(), key=lambda x: (-x[1], x[0])))

    return {
        "analyzed_comment_count": analyzed_count,
        **counts,
        "weighted_quality_sum": round(weighted_sum, 4),
        "comment_quality_ratio": round(quality_ratio, 4),
        "adjusted_comment_count": round(adjusted_comment_count, 2),
        "comment_quality_summary": summary,
    }
