"""Run Suno update tasks with Supabase as the backing store.

This keeps the existing CSV-compatible processing modules, but reads/writes those
CSV-shaped tables from/to Supabase raw tables instead of encrypted data-branch ZIPs.

Modes:
- full: new songs + existing refresh + queue + comments + rank + loudness + payload
- new: new song discovery + queue + payload
- existing: tiered existing refresh + comments + rank + loudness + payload
- comments: incremental comment fetch/analysis only + payload
- loudness: loudness only + payload
- payload: rebuild app_payloads.latest only
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
    parser.add_argument("--mode", choices=["full", "new", "existing", "comments", "loudness", "payload"], default="existing")
    parser.add_argument("--max-update-rows", default=os.getenv("MAX_UPDATE_ROWS", "1200"))
    parser.add_argument("--skip-loudness", action="store_true", default=os.getenv("SKIP_LOUDNESS", "0").lower() in {"1", "true", "yes"})
    parser.add_argument("--skip-comments", action="store_true", default=os.getenv("SKIP_COMMENT_QUALITY", "0").lower() in {"1", "true", "yes"})
    args = parser.parse_args()

    print(f"[supabase_update] mode={args.mode}")
    pull_tables_to_csv()

    base_env = {
        "PYTHONPATH": str(ROOT / "scripts"),
        "KEEP_EXPIRED_SONGS_IN_DB": "1",
        "MAX_UPDATE_ROWS": args.max_update_rows,
        "UPDATE_TIERING_ENABLED": os.getenv("UPDATE_TIERING_ENABLED", "1"),
        "COMPACT_HISTORY": os.getenv("COMPACT_HISTORY", "1"),
        "COMMENT_DB_ENABLED": os.getenv("COMMENT_DB_ENABLED", "1"),
    }

    if args.mode in {"full", "new", "existing"}:
        fetch_new = args.mode in {"full", "new"}
        env = dict(base_env)
        env["FETCH_NEW_SONGS"] = "1" if fetch_new else "0"
        if args.mode == "new":
            env["MAX_UPDATE_ROWS"] = os.getenv("NEW_MODE_MAX_UPDATE_ROWS", "0")
        run([sys.executable, "scripts/update_public_song_pages.py"], env=env)
        run([sys.executable, "scripts/process_manual_queue.py"], env=env, optional=True)

    if args.mode in {"full", "existing", "comments"} and not args.skip_comments:
        run([sys.executable, "scripts/analyze_comment_quality.py"], env=base_env, optional=False)

    if args.mode in {"full", "existing"}:
        run([sys.executable, "scripts/update_rank_movement.py"], env=base_env, optional=True)

    if args.mode in {"full", "existing", "loudness"} and not args.skip_loudness:
        run([sys.executable, "scripts/analyze_loudness.py"], env=base_env, optional=True)

    run([sys.executable, "scripts/build_app_payload.py"], env=base_env)

    if args.mode != "payload":
        push_csv_to_tables(replace=True)
    push_app_payload()

    print("[supabase_update] done")


if __name__ == "__main__":
    main()
