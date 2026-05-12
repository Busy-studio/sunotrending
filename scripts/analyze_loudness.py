"""Analyze Suno audio loudness and store playback normalization metadata.

This script performs a lightweight ReplayGain-style analysis using ffmpeg's
loudnorm filter. It does not modify audio files; it stores metadata in the DB
so the web player can apply gain at playback time.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from ranking_core import serialize_datetime_columns_for_csv
except Exception:  # pragma: no cover
    serialize_datetime_columns_for_csv = None

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "suno_song_db.csv"

TARGET_LUFS = float(os.getenv("LOUDNESS_TARGET_LUFS", "-14.0"))
TRUE_PEAK_CEILING_DB = float(os.getenv("LOUDNESS_TRUE_PEAK_CEILING_DB", "-1.0"))
MAX_BOOST_DB = float(os.getenv("LOUDNESS_MAX_BOOST_DB", "6.0"))
MAX_CUT_DB = float(os.getenv("LOUDNESS_MAX_CUT_DB", "-12.0"))
MAX_ITEMS = int(os.getenv("LOUDNESS_ANALYZE_MAX_ITEMS", "30"))
PRIORITY_TOP_N = int(os.getenv("LOUDNESS_PRIORITY_TOP_N", "300"))
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("LOUDNESS_FFMPEG_TIMEOUT_SECONDS", "180"))
REQUEST_USER_AGENT = os.getenv(
    "LOUDNESS_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
)

LOUDNESS_COLUMNS = [
    "integrated_lufs",
    "true_peak_db",
    "loudness_gain_db",
    "loudness_target_lufs",
    "loudness_true_peak_ceiling_db",
    "loudness_checked_at",
    "loudness_status",
    "loudness_error",
    "loudness_audio_url_hash",
    "loudness_input_lra",
    "loudness_input_thresh",
    "loudness_target_offset",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    s = str(value).strip()
    return not s or s.lower() in {"nan", "none", "null", "<na>", "-"}


def safe_float(value: Any) -> float | None:
    try:
        if is_blank(value):
            return None
        n = float(value)
        if not math.isfinite(n):
            return None
        return n
    except Exception:
        return None


def audio_url_hash(url: str) -> str:
    return hashlib.sha256(str(url).encode("utf-8", errors="ignore")).hexdigest()[:24]


def clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def compute_gain_db(integrated_lufs: float, true_peak_db: float) -> float:
    target_gain = TARGET_LUFS - integrated_lufs
    peak_limited_gain = TRUE_PEAK_CEILING_DB - true_peak_db
    gain = min(target_gain, peak_limited_gain)
    return round(clamp(gain, MAX_CUT_DB, MAX_BOOST_DB), 3)


def extract_loudnorm_json(stderr_text: str) -> dict[str, Any]:
    # ffmpeg prints other logs around a JSON object. Grab the last JSON-looking block.
    matches = re.findall(r"\{\s*\"input_i\".*?\}", stderr_text, flags=re.DOTALL)
    if not matches:
        raise ValueError("ffmpeg loudnorm JSON was not found")
    return json.loads(matches[-1])


def run_ffmpeg_loudnorm(audio_url: str) -> dict[str, Any]:
    headers = "\r\n".join([
        f"User-Agent: {REQUEST_USER_AGENT}",
        "Referer: https://suno.com/",
        "Origin: https://suno.com",
    ]) + "\r\n"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-headers",
        headers,
        "-i",
        audio_url,
        "-af",
        f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK_CEILING_DB}:LRA=11:print_format=json",
        "-f",
        "null",
        "-",
    ]

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )

    stderr = proc.stderr or ""
    if proc.returncode != 0 and "input_i" not in stderr:
        tail = stderr.strip().splitlines()[-8:]
        raise RuntimeError("ffmpeg failed: " + " | ".join(tail))

    raw = extract_loudnorm_json(stderr)
    integrated_lufs = safe_float(raw.get("input_i"))
    true_peak_db = safe_float(raw.get("input_tp"))

    if integrated_lufs is None or true_peak_db is None:
        raise ValueError(f"invalid loudnorm result: input_i={raw.get('input_i')} input_tp={raw.get('input_tp')}")

    gain_db = compute_gain_db(integrated_lufs, true_peak_db)

    return {
        "integrated_lufs": round(integrated_lufs, 3),
        "true_peak_db": round(true_peak_db, 3),
        "loudness_gain_db": gain_db,
        "loudness_target_lufs": TARGET_LUFS,
        "loudness_true_peak_ceiling_db": TRUE_PEAK_CEILING_DB,
        "loudness_input_lra": safe_float(raw.get("input_lra")),
        "loudness_input_thresh": safe_float(raw.get("input_thresh")),
        "loudness_target_offset": safe_float(raw.get("target_offset")),
        "loudness_status": "ok",
        "loudness_error": "",
    }


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in LOUDNESS_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df


def needs_analysis(row: pd.Series) -> bool:
    audio_url = str(row.get("audio_url", "") or "").strip()
    if not audio_url:
        return False

    current_hash = audio_url_hash(audio_url)
    stored_hash = str(row.get("loudness_audio_url_hash", "") or "").strip()
    status = str(row.get("loudness_status", "") or "").strip().lower()

    if current_hash != stored_hash:
        return True
    if status != "ok":
        return True
    for col in ["integrated_lufs", "true_peak_db", "loudness_gain_db"]:
        if safe_float(row.get(col)) is None:
            return True
    return False


def select_rows_to_analyze(df: pd.DataFrame) -> list[int]:
    candidates = []
    for idx, row in df.iterrows():
        if needs_analysis(row):
            candidates.append(idx)

    if not candidates:
        return []

    cdf = df.loc[candidates].copy()

    # Prefer current chart/ranked songs, then newer active rows.
    cdf["__rank"] = pd.to_numeric(cdf.get("current_rank", pd.Series([None] * len(cdf), index=cdf.index)), errors="coerce")
    cdf["__priority_rank"] = cdf["__rank"].where(
        cdf["__rank"].between(1, PRIORITY_TOP_N),
        999999,
    )
    cdf["__created_at"] = pd.to_datetime(cdf.get("created_at", None), errors="coerce", utc=True)
    cdf["__created_sort"] = cdf["__created_at"].fillna(pd.Timestamp("1970-01-01", tz="UTC"))
    cdf = cdf.sort_values(["__priority_rank", "__created_sort"], ascending=[True, False])
    return [int(i) for i in cdf.index.tolist()[:MAX_ITEMS]]


def main() -> None:
    if not DB_PATH.exists():
        print(f"[loudness] {DB_PATH} not found. Skipping.")
        return

    df = pd.read_csv(DB_PATH)
    if df.empty:
        print("[loudness] DB empty. Skipping.")
        return

    df = ensure_columns(df)
    indices = select_rows_to_analyze(df)

    if MAX_ITEMS <= 0:
        print("[loudness] LOUDNESS_ANALYZE_MAX_ITEMS <= 0. Skipping analysis.")
        return

    print(f"[loudness] candidates_selected={len(indices)} max_items={MAX_ITEMS}")

    ok_count = 0
    fail_count = 0
    checked_at = utc_now_iso()

    for idx in indices:
        song_id = str(df.at[idx, "id"] if "id" in df.columns else "")
        title = str(df.at[idx, "title"] if "title" in df.columns else "")[:80]
        audio_url = str(df.at[idx, "audio_url"] or "").strip()
        current_hash = audio_url_hash(audio_url)

        print(f"[loudness] analyze id={song_id} title={title!r}")
        try:
            result = run_ffmpeg_loudnorm(audio_url)
            for key, value in result.items():
                df.at[idx, key] = value
            df.at[idx, "loudness_checked_at"] = checked_at
            df.at[idx, "loudness_audio_url_hash"] = current_hash
            ok_count += 1
            print(
                "[loudness] ok "
                f"id={song_id} I={result['integrated_lufs']} TP={result['true_peak_db']} "
                f"gain={result['loudness_gain_db']}"
            )
        except Exception as exc:
            fail_count += 1
            err = str(exc).replace("\n", " ")[:500]
            df.at[idx, "loudness_status"] = "failed"
            df.at[idx, "loudness_error"] = err
            df.at[idx, "loudness_checked_at"] = checked_at
            df.at[idx, "loudness_audio_url_hash"] = current_hash
            print(f"[loudness] failed id={song_id}: {err}")

    if serialize_datetime_columns_for_csv is not None:
        try:
            df = serialize_datetime_columns_for_csv(df)
        except Exception:
            pass

    df.to_csv(DB_PATH, index=False, encoding="utf-8-sig")
    print(f"[loudness] saved {DB_PATH} ok={ok_count} failed={fail_count}")


if __name__ == "__main__":
    main()
