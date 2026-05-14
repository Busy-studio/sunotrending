"""Run Suno update pipeline with Supabase as the backing store.

Supabase 운영 모드에서는 기존 CSV 처리 스크립트를 재사용하되, 시작/끝 저장소만
Supabase raw text tables로 바꾼다.

Modes / stages:
- full:     신규곡 + 기존곡 + 수동 queue + 댓글품질 + 순위 + LUFS + payload
- new:      신규곡/수동 queue 중심 + 순위 + payload (기존곡 상세 갱신 없음)
- existing: 기존곡 상세 갱신 + 순위 + payload
- comments: 댓글 품질 분석 + payload
- loudness: LUFS 분석 + payload
- payload:  payload만 재생성
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


def run_update_public(fetch_new: bool, max_update_rows: str, env_base: dict):
    env = {
        **env_base,
        "FETCH_NEW_SONGS": "1" if fetch_new else "0",
        "MAX_UPDATE_ROWS": str(max_update_rows),
    }
    run([sys.executable, "scripts/update_public_song_pages.py"], env=env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["full", "new", "existing", "comments", "loudness", "payload"],
        default="existing",
    )
    parser.add_argument("--max-update-rows", default=os.getenv("MAX_UPDATE_ROWS", "1200"))
    parser.add_argument("--new-max-update-rows", default=os.getenv("NEW_MAX_UPDATE_ROWS", "0"))
    parser.add_argument("--skip-loudness", action="store_true", default=os.getenv("SKIP_LOUDNESS", "0").lower() in {"1", "true", "yes"})
    parser.add_argument("--skip-comments", action="store_true", default=os.getenv("SKIP_COMMENT_QUALITY", "0").lower() in {"1", "true", "yes"})
    args = parser.parse_args()

    print(f"[supabase_update] mode={args.mode}")

    # 1) Pull latest Supabase state into local CSV filenames expected by existing scripts.
    pull_tables_to_csv()

    env_base = {
        "PYTHONPATH": str(ROOT / "scripts"),
        # Supabase 모드에서는 4일 지난 곡도 suno_songs에 계속 남긴다.
        "KEEP_EXPIRED_SONGS_IN_DB": "1",
    }

    # 2) Run only the requested stage(s). Split workflows can call these independently.
    if args.mode == "full":
        run_update_public(fetch_new=True, max_update_rows=args.max_update_rows, env_base=env_base)
        run([sys.executable, "scripts/process_manual_queue.py"], env=env_base, optional=True)
        if not args.skip_comments:
            run([sys.executable, "scripts/analyze_comment_quality.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/update_rank_movement.py"], env=env_base, optional=True)
        if not args.skip_loudness:
            run([sys.executable, "scripts/analyze_loudness.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/build_app_payload.py"], env=env_base)

    elif args.mode == "new":
        # 신규곡 feed와 수동 queue만 빠르게 반영한다. 기존곡 상세 업데이트는 별도 workflow가 담당.
        run_update_public(fetch_new=True, max_update_rows=args.new_max_update_rows, env_base=env_base)
        run([sys.executable, "scripts/process_manual_queue.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/update_rank_movement.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/build_app_payload.py"], env=env_base)

    elif args.mode == "existing":
        run_update_public(fetch_new=False, max_update_rows=args.max_update_rows, env_base=env_base)
        run([sys.executable, "scripts/update_rank_movement.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/build_app_payload.py"], env=env_base)

    elif args.mode == "comments":
        run([sys.executable, "scripts/analyze_comment_quality.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/update_rank_movement.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/build_app_payload.py"], env=env_base)

    elif args.mode == "loudness":
        run([sys.executable, "scripts/analyze_loudness.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/build_app_payload.py"], env=env_base)

    elif args.mode == "payload":
        run([sys.executable, "scripts/update_rank_movement.py"], env=env_base, optional=True)
        run([sys.executable, "scripts/build_app_payload.py"], env=env_base)

    # 3) Push state and latest payload back to Supabase.
    push_csv_to_tables(replace=True)
    push_app_payload()

    print("[supabase_update] done")


if __name__ == "__main__":
    main()
