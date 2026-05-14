"""Run the existing Suno update pipeline with Supabase as the backing store.

This script intentionally reuses the current CSV-based processing modules in a
local temporary `data/` folder, but reads/writes those CSV-shaped tables from/to
Supabase instead of the encrypted data-branch ZIP files.

Modes:
- full: fetch new songs + update existing rows
- existing: update existing rows only
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from supabase_raw_io import pull_tables_to_csv, push_app_payload, push_csv_to_tables

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, env=None, optional=False):
    print(f"[run] {' '.join(cmd)}")
    merged_env = os.environ.copy()
    if env:
        merged_env.update({k: str(v) for k, v in env.items()})
    result = subprocess.run(cmd, cwd=ROOT, env=merged_env)
    if result.returncode != 0:
        msg = f"Command failed ({result.returncode}): {' '.join(cmd)}"
        if optional:
            print(f"[optional_failed] {msg}")
        else:
            raise SystemExit(msg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full", "existing"], default="existing")
    parser.add_argument("--max-update-rows", default=os.getenv("MAX_UPDATE_ROWS", "1200"))
    parser.add_argument("--skip-loudness", action="store_true", default=os.getenv("SKIP_LOUDNESS", "0").lower() in {"1", "true", "yes"})
    parser.add_argument("--skip-comments", action="store_true", default=os.getenv("SKIP_COMMENT_QUALITY", "0").lower() in {"1", "true", "yes"})
    args = parser.parse_args()

    print(f"[supabase_update] mode={args.mode}")

    # 1) Pull Supabase raw tables into the local CSV filenames expected by the existing scripts.
    pull_tables_to_csv()

    # 2) Run the current update pipeline. The important change is KEEP_EXPIRED_SONGS_IN_DB=1:
    #    old songs remain in suno_songs, and 4-day eligibility is handled only by payload/ranking filters.
    env = {
        "PYTHONPATH": str(ROOT / "scripts"),
        "FETCH_NEW_SONGS": "1" if args.mode == "full" else "0",
        "KEEP_EXPIRED_SONGS_IN_DB": "1",
        "MAX_UPDATE_ROWS": args.max_update_rows,
    }

    run([sys.executable, "scripts/update_public_song_pages.py"], env=env)

    # Manual queue can still be kept in Supabase raw table, but it writes through CSV locally.
    run([sys.executable, "scripts/process_manual_queue.py"], env=env, optional=True)

    if not args.skip_comments:
        run([sys.executable, "scripts/analyze_comment_quality.py"], env=env, optional=True)

    run([sys.executable, "scripts/update_rank_movement.py"], env=env, optional=True)

    if not args.skip_loudness:
        run([sys.executable, "scripts/analyze_loudness.py"], env=env, optional=True)

    run([sys.executable, "scripts/build_app_payload.py"], env=env)

    # 3) Push the CSV-shaped state and latest payload back to Supabase.
    push_csv_to_tables(replace=True)
    push_app_payload()

    print("[supabase_update] done")


if __name__ == "__main__":
    main()
