#!/usr/bin/env python3
"""
Migrate Suno Trending exported CSV/JSON files into Supabase.

Expected input directory:
  data/
    suno_song_db.csv
    suno_song_history.csv
    suno_rank_history.csv
    suno_song_archive.csv
    manual_song_queue.csv
    suno_app_payload.json

Usage:
  export SUPABASE_URL="https://xxxx.supabase.co"
  export SUPABASE_SERVICE_ROLE_KEY="..."
  python scripts/migrate_csv_to_supabase.py --data-dir ./data

You may also place the env vars in a local .env file in the current working directory.
Never commit .env or service role keys to GitHub.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from supabase import create_client


CSV_TABLES = [
    {
        "file": "suno_song_db.csv",
        "table": "suno_songs",
        "mode": "upsert",
        "conflict": "id",
        "required": ["id"],
    },
    {
        "file": "suno_song_history.csv",
        "table": "suno_song_history",
        "mode": "upsert",
        "conflict": "id,checked_at",
        "required": ["id", "checked_at"],
    },
    {
        "file": "suno_rank_history.csv",
        "table": "suno_rank_history",
        "mode": "upsert",
        "conflict": "id,captured_at",
        "required": ["id", "captured_at"],
    },
    {
        "file": "suno_song_archive.csv",
        "table": "suno_song_archive",
        "mode": "upsert",
        "conflict": "id",
        "required": ["id"],
    },
    {
        "file": "manual_song_queue.csv",
        "table": "manual_song_queue",
        "mode": "upsert",
        "conflict": "request_id",
        "required": ["request_id"],
    },
]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    # pandas NA / NaT
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def clean_value(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


def clean_records(df: pd.DataFrame, required: list[str]) -> list[dict[str, Any]]:
    # Convert all rows to JSON-safe dicts. raw preserves full original CSV columns.
    records: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        cleaned = {k: clean_value(v) for k, v in row.items()}
        if any(not cleaned.get(col) for col in required):
            continue
        cleaned["raw"] = cleaned.copy()
        records.append(cleaned)
    return records


def chunked(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def execute_batch(sb, table: str, rows: list[dict[str, Any]], *, mode: str, conflict: str | None, chunk_size: int, dry_run: bool) -> int:
    if not rows:
        print(f"- {table}: 0 rows")
        return 0

    total = 0
    chunks = list(chunked(rows, chunk_size))
    for idx, batch in enumerate(chunks, 1):
        if dry_run:
            total += len(batch)
            continue
        if mode == "upsert":
            query = sb.table(table).upsert(batch, on_conflict=conflict)
        elif mode == "insert":
            query = sb.table(table).insert(batch)
        else:
            raise ValueError(f"Unsupported mode: {mode}")
        query.execute()
        total += len(batch)
        print(f"  {table}: uploaded chunk {idx}/{len(chunks)} ({total}/{len(rows)})")
    return total


def migrate_csv(sb, data_dir: Path, spec: dict[str, Any], *, chunk_size: int, dry_run: bool) -> int:
    path = data_dir / spec["file"]
    if not path.exists():
        print(f"- SKIP missing file: {path}")
        return 0

    df = pd.read_csv(path, dtype=object, keep_default_na=True)
    if df.empty:
        print(f"- {spec['table']}: CSV exists but has 0 rows")
        return 0

    records = clean_records(df, spec["required"])
    print(f"- {spec['file']} -> {spec['table']}: {len(records)} rows prepared")
    return execute_batch(
        sb,
        spec["table"],
        records,
        mode=spec["mode"],
        conflict=spec.get("conflict"),
        chunk_size=chunk_size,
        dry_run=dry_run,
    )


def migrate_payload(sb, data_dir: Path, *, dry_run: bool) -> int:
    path = data_dir / "suno_app_payload.json"
    if not path.exists():
        print(f"- SKIP missing file: {path}")
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = payload.get("meta") if isinstance(payload, dict) else {}
    row = {
        "key": "latest",
        "payload_json": payload,
        "source": "csv_migration",
        "meta": meta or {},
    }
    print("- suno_app_payload.json -> app_payloads: key='latest'")
    if not dry_run:
        sb.table("app_payloads").upsert(row, on_conflict="key").execute()
    return 1


def print_counts(sb) -> None:
    tables = [
        "suno_songs",
        "suno_song_history",
        "suno_rank_history",
        "suno_song_archive",
        "manual_song_queue",
        "app_payloads",
    ]
    print("\nSupabase row counts:")
    for table in tables:
        try:
            res = sb.table(table).select("*", count="exact").limit(1).execute()
            print(f"- {table}: {res.count}")
        except Exception as exc:
            print(f"- {table}: count failed ({exc})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Suno Trending CSV/JSON files to Supabase")
    parser.add_argument("--data-dir", default="data", help="Directory containing exported CSV/JSON files")
    parser.add_argument("--chunk-size", type=int, default=200, help="Rows per Supabase request")
    parser.add_argument("--dry-run", action="store_true", help="Parse files and print counts without uploading")
    parser.add_argument("--skip-payload", action="store_true", help="Do not upload suno_app_payload.json")
    args = parser.parse_args()

    load_dotenv(Path(".env"))
    data_dir = Path(args.data_dir).expanduser().resolve()
    if not data_dir.exists():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        return 2

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not args.dry_run and (not url or not key):
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.", file=sys.stderr)
        print("Set them as environment variables or create a local .env file.", file=sys.stderr)
        return 2

    sb = None if args.dry_run else create_client(url, key)

    print(f"Data directory: {data_dir}")
    print(f"Dry run: {args.dry_run}")
    uploaded = 0
    for spec in CSV_TABLES:
        uploaded += migrate_csv(sb, data_dir, spec, chunk_size=args.chunk_size, dry_run=args.dry_run)
    if not args.skip_payload:
        uploaded += migrate_payload(sb, data_dir, dry_run=args.dry_run)

    print(f"\nDone. Prepared/uploaded units: {uploaded}")
    if sb is not None:
        print_counts(sb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
