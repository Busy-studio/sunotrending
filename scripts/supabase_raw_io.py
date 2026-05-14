"""Read/write Suno CSV-shaped tables from Supabase raw text tables."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd
from supabase import create_client

DATA_DIR = Path("data")

TABLE_TO_FILE = {
    "suno_songs": DATA_DIR / "suno_song_db.csv",
    "suno_song_history": DATA_DIR / "suno_song_history.csv",
    "suno_rank_history": DATA_DIR / "suno_rank_history.csv",
    "manual_song_queue": DATA_DIR / "manual_song_queue.csv",
    # Legacy only. Supabase migration no longer needs to move songs into archive,
    # but keeping this lets older scripts that expect the file keep running.
    "suno_song_archive": DATA_DIR / "suno_song_archive.csv",
}


TABLE_COLUMNS = {
    "suno_songs": ['id', 'title', 'handle', 'display_name', 'user_id', 'created_at', 'first_seen_at', 'last_checked_at', 'play_count', 'upvote_count', 'comment_count', 'flag_count', 'is_contest_clip', 'contest_ids', 'download_disabled_reason', 'is_public', 'is_hidden', 'is_trashed', 'explicit', 'model', 'major_model_version', 'display_tags', 'duration', 'lyrics', 'prompt', 'gpt_description_prompt', 'song_url', 'audio_url', 'image_url', 'source', 'effective_comment_count', 'integrated_lufs', 'true_peak_db', 'loudness_gain_db', 'loudness_target_lufs', 'loudness_true_peak_ceiling_db', 'loudness_checked_at', 'loudness_status', 'loudness_error', 'loudness_audio_url_hash', 'loudness_input_lra', 'loudness_input_thresh', 'loudness_target_offset', 'adjusted_comment_count', 'comment_quality_ratio', 'analyzed_comment_count', 'meaningful_count', 'generic_count', 'mention_only_count', 'emoji_only_count', 'comment_quality_summary', 'comment_quality_checked_at', 'current_rank', 'previous_rank', 'rank_change', 'rank_status', 'current_score', 'base_score', 'growth_score', 'freshness_score', 'best_rank', 'best_trend_score', 'best_score_at', 'peak_play_count', 'peak_upvote_count', 'peak_comment_count', 'peak_adjusted_comment_count'],
    "suno_song_history": ['checked_at', 'id', 'title', 'handle', 'created_at', 'play_count', 'upvote_count', 'comment_count', 'flag_count'],
    "suno_rank_history": ['captured_at', 'id', 'rank', 'trend_score', 'base_score', 'growth_score', 'freshness_score', 'play_count', 'upvote_count', 'comment_count', 'adjusted_comment_count'],
    "manual_song_queue": ['request_id', 'submitted_at', 'url', 'status', 'song_id', 'title', 'processed_at', 'error'],
    "suno_song_archive": ['archived_at', 'archive_reason', 'id', 'title', 'handle', 'display_name', 'user_id', 'created_at', 'first_seen_at', 'last_checked_at', 'play_count', 'upvote_count', 'comment_count', 'adjusted_comment_count', 'comment_quality_ratio', 'meaningful_count', 'generic_count', 'mention_only_count', 'emoji_only_count', 'flag_count', 'final_rank', 'best_rank', 'final_trend_score', 'final_base_score', 'final_growth_score', 'final_freshness_score', 'best_trend_score', 'best_score_at', 'peak_play_count', 'peak_upvote_count', 'peak_comment_count', 'peak_adjusted_comment_count', 'model', 'major_model_version', 'display_tags', 'duration', 'lyrics', 'prompt', 'gpt_description_prompt', 'song_url', 'audio_url', 'image_url', 'source'],
}

CLEAR_FILTER_COLUMN = {
    "suno_songs": "id",
    "suno_song_history": "id",
    "suno_rank_history": "id",
    "manual_song_queue": "request_id",
    "suno_song_archive": "id",
    "app_payloads": "key",
}


def get_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url:
        raise RuntimeError("SUPABASE_URL is missing")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is missing")
    return create_client(url, key)


def _fetch_all(sb, table: str, page_size: int = 1000) -> List[dict]:
    rows: List[dict] = []
    start = 0
    while True:
        end = start + page_size - 1
        result = sb.table(table).select("*").range(start, end).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def pull_tables_to_csv(tables: Optional[Iterable[str]] = None) -> Dict[str, int]:
    sb = get_client()
    DATA_DIR.mkdir(exist_ok=True)
    counts: Dict[str, int] = {}
    for table, path in TABLE_TO_FILE.items():
        if tables and table not in tables:
            continue
        rows = _fetch_all(sb, table)
        df = pd.DataFrame(rows)
        # Supabase may include no rows and therefore no columns; keep expected empty file if available.
        df.to_csv(path, index=False, encoding="utf-8-sig")
        counts[table] = len(df)
        print(f"[supabase_pull] {table}: {len(df)} rows -> {path}")
    return counts


def _clean_cell(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _records_from_csv(path: Path, table: str) -> List[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    allowed = TABLE_COLUMNS.get(table)
    if allowed:
        for col in allowed:
            if col not in df.columns:
                df[col] = ""
        df = df[allowed].copy()

    records = []
    for row in df.to_dict(orient="records"):
        records.append({k: _clean_cell(v) for k, v in row.items()})
    return records


def _clear_table(sb, table: str):
    col = CLEAR_FILTER_COLUMN.get(table)
    if not col:
        raise RuntimeError(f"No clear filter configured for {table}")
    # Delete every row without relying on typed ids. or_ handles empty/null key rows too.
    try:
        sb.table(table).delete().or_(f"{col}.neq.__never_match__,{col}.is.null").execute()
    except Exception as exc:
        raise RuntimeError(f"Failed to clear {table}: {exc}") from exc


def _insert_chunks(sb, table: str, records: List[dict], chunk_size: int = 500):
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        if chunk:
            sb.table(table).insert(chunk).execute()


def push_csv_to_tables(tables: Optional[Iterable[str]] = None, replace: bool = True) -> Dict[str, int]:
    sb = get_client()
    counts: Dict[str, int] = {}
    for table, path in TABLE_TO_FILE.items():
        if tables and table not in tables:
            continue
        records = _records_from_csv(path, table)
        if replace:
            _clear_table(sb, table)
        _insert_chunks(sb, table, records)
        counts[table] = len(records)
        print(f"[supabase_push] {table}: {len(records)} rows <- {path}")
    return counts


def push_app_payload(payload_path: Path = DATA_DIR / "suno_app_payload.json") -> bool:
    sb = get_client()
    if not payload_path.exists():
        print(f"[supabase_payload] missing {payload_path}, skipped")
        return False
    payload_text = payload_path.read_text(encoding="utf-8")
    # Replace latest row. This works whether payload_json is text or jsonb-compatible.
    sb.table("app_payloads").upsert(
        {"key": "latest", "payload_json": payload_text},
        on_conflict="key",
    ).execute()
    print(f"[supabase_payload] uploaded latest from {payload_path} bytes={len(payload_text.encode('utf-8'))}")
    return True
