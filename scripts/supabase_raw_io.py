"""Read/write Suno CSV-shaped tables from Supabase raw text tables.

Supabase 운영 전환 후 기준:
- suno_songs는 전체 곡을 계속 보관한다.
- 4일 지난 곡은 Top 200 후보에서만 제외한다.
- suno_song_archive는 legacy/선택 기록용으로만 남기고, 기본 pull/push 대상에서 제외한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd
from pandas.errors import EmptyDataError
from supabase import create_client

DATA_DIR = Path("data")

# 운영 테이블만 기본 동기화한다. archive는 더 이상 active DB에서 곡을 빼는 용도가 아니다.
TABLE_TO_FILE = {
    "suno_songs": DATA_DIR / "suno_song_db.csv",
    "suno_song_history": DATA_DIR / "suno_song_history.csv",
    "suno_rank_history": DATA_DIR / "suno_rank_history.csv",
    "manual_song_queue": DATA_DIR / "manual_song_queue.csv",
}

# 오래된 스크립트 호환용으로만 빈 파일을 만들어 둔다. Supabase에는 push하지 않는다.
LEGACY_EMPTY_FILES = {
    "suno_song_archive": DATA_DIR / "suno_song_archive.csv",
}

TABLE_COLUMNS = {
    "suno_songs": ['id', 'title', 'handle', 'display_name', 'user_id', 'created_at', 'first_seen_at', 'last_checked_at', 'play_count', 'upvote_count', 'comment_count', 'flag_count', 'is_contest_clip', 'contest_ids', 'download_disabled_reason', 'is_public', 'is_hidden', 'is_trashed', 'explicit', 'model', 'major_model_version', 'display_tags', 'duration', 'lyrics', 'prompt', 'gpt_description_prompt', 'song_url', 'audio_url', 'image_url', 'source', 'effective_comment_count', 'integrated_lufs', 'true_peak_db', 'loudness_gain_db', 'loudness_target_lufs', 'loudness_true_peak_ceiling_db', 'loudness_checked_at', 'loudness_status', 'loudness_error', 'loudness_audio_url_hash', 'loudness_input_lra', 'loudness_input_thresh', 'loudness_target_offset', 'adjusted_comment_count', 'comment_quality_ratio', 'analyzed_comment_count', 'meaningful_count', 'generic_count', 'mention_only_count', 'emoji_only_count', 'comment_quality_summary', 'comment_quality_checked_at', 'current_rank', 'previous_rank', 'rank_change', 'rank_status', 'current_score', 'base_score', 'growth_score', 'freshness_score', 'best_rank', 'best_trend_score', 'best_score_at', 'peak_play_count', 'peak_upvote_count', 'peak_comment_count', 'peak_adjusted_comment_count', 'status', 'update_tier', 'next_check_at', 'fetch_fail_count', 'last_fetch_error', 'last_change_at', 'playlist_ref_count', 'comments_fetch_needed', 'last_comment_fetch_at'],
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


def _write_empty_csv_with_header(path: Path, table: str) -> None:
    cols = TABLE_COLUMNS.get(table, [])
    pd.DataFrame(columns=cols).to_csv(path, index=False, encoding="utf-8-sig")


def pull_tables_to_csv(tables: Optional[Iterable[str]] = None) -> Dict[str, int]:
    sb = get_client()
    DATA_DIR.mkdir(exist_ok=True)
    requested = set(tables) if tables else None
    counts: Dict[str, int] = {}

    for table, path in TABLE_TO_FILE.items():
        if requested and table not in requested:
            continue
        rows = _fetch_all(sb, table)
        if rows:
            df = pd.DataFrame(rows)
            allowed = TABLE_COLUMNS.get(table)
            if allowed:
                for col in allowed:
                    if col not in df.columns:
                        df[col] = ""
                df = df[allowed].copy()
            df.to_csv(path, index=False, encoding="utf-8-sig")
        else:
            _write_empty_csv_with_header(path, table)
        counts[table] = len(rows)
        print(f"[supabase_pull] {table}: {len(rows)} rows -> {path}")

    # Legacy compatibility only. Do not pull archive from Supabase by default.
    for table, path in LEGACY_EMPTY_FILES.items():
        if requested and table not in requested:
            continue
        if not path.exists() or path.stat().st_size == 0:
            _write_empty_csv_with_header(path, table)
            print(f"[supabase_pull] {table}: legacy empty file prepared -> {path}")

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
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except EmptyDataError:
        return []

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
    requested = set(tables) if tables else None
    counts: Dict[str, int] = {}

    for table, path in TABLE_TO_FILE.items():
        if requested and table not in requested:
            continue
        records = _records_from_csv(path, table)
        if replace:
            _clear_table(sb, table)
        _insert_chunks(sb, table, records)
        counts[table] = len(records)
        print(f"[supabase_push] {table}: {len(records)} rows <- {path}")

    if requested and "suno_song_archive" in requested:
        print("[supabase_push] suno_song_archive skipped: archive is legacy-only in Supabase mode")

    return counts


def push_app_payload(payload_path: Path = DATA_DIR / "suno_app_payload.json") -> bool:
    sb = get_client()
    if not payload_path.exists():
        print(f"[supabase_payload] missing {payload_path}, skipped")
        return False

    payload_text = payload_path.read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    sb.table("app_payloads").upsert(
        {"key": "latest", "payload_json": payload},
        on_conflict="key",
    ).execute()
    print(f"[supabase_payload] uploaded latest from {payload_path} bytes={len(payload_text.encode('utf-8'))}")
    return True
