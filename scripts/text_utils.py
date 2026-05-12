"""Shared text normalization helpers for Suno metadata.

Suno responses sometimes contain UTF-8 text that has already been decoded as
latin1/cp1252, leaving mojibake strings such as ``ÐÐ¾ÑÐµ`` or ``ì´ì`` in the
CSV. Normalize text before it is stored so app/search/archive data stays clean.
"""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

try:
    import ftfy
except Exception:  # pragma: no cover - optional dependency
    ftfy = None

BLANK_STRINGS = {"", "nan", "none", "null", "undefined", "<na>", "nat", "-"}

# Text-ish columns that should be safe to mojibake-fix at storage time.
# URLs and IDs are deliberately excluded.
TEXT_COLUMNS = [
    "title",
    "handle",
    "display_name",
    "artist_display_name",
    "model",
    "major_model_version",
    "display_tags",
    "lyrics",
    "prompt",
    "gpt_description_prompt",
    "comment_quality_summary",
    "source",
]


def is_blank_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    if isinstance(value, dict):
        return True
    if isinstance(value, list):
        return len(value) == 0
    s = str(value).strip()
    if s.lower() in BLANK_STRINGS:
        return True
    # Next.js / RSC reference tokens such as $5b, $12, $abc.
    if s.startswith("$") and len(s) <= 8:
        return True
    return False


def broken_score(s: str) -> int:
    if not s:
        return 999_999

    # Markers commonly left by UTF-8 bytes decoded as latin1/cp1252.
    bad_markers = [
        "Ã", "ã", "Â", "â", "ð", "Ð", "Ñ", "Î", "Ï",
        "Å", "¤", "¦", "§", "¨", "©", "ª", "«", "¬", "®", "¯", "°", "±", "²", "³",
        "ì", "í", "ë", "ê", "è", "é", "ç",
    ]
    score = sum(s.count(ch) * 3 for ch in bad_markers)
    score += sum(5 for ch in s if 0x80 <= ord(ch) <= 0x9F)
    score += max(0, 8 - len(s))
    return score


def try_decode_utf8_from_latinish(s: str) -> list[str]:
    candidates: list[str] = []
    for enc in ("latin1", "cp1252"):
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
    if is_blank_value(value):
        return ""

    original = str(value)
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
        new_frontier: list[str] = []
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
    s = fix_mojibake(value).strip()
    if s.lower() in BLANK_STRINGS:
        return ""
    return s


def clean_list_or_text(value: Any) -> str:
    if is_blank_value(value):
        return ""
    if isinstance(value, list):
        cleaned = [clean_text(x) for x in value if not is_blank_value(x)]
        return ", ".join([x for x in cleaned if x])
    return clean_text(value)


def normalize_text_columns(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Return a copy with mojibake fixed in known text metadata columns."""
    if df is None or df.empty:
        return df
    out = df.copy()
    target_columns = list(columns) if columns is not None else TEXT_COLUMNS
    for col in target_columns:
        if col in out.columns:
            out[col] = out[col].apply(clean_text)
    return out


def normalize_record_text(record: dict[str, Any], columns: Iterable[str] | None = None) -> dict[str, Any]:
    """Normalize text fields in a row dict without touching numeric/url/id fields."""
    out = dict(record)
    target_columns = set(columns or TEXT_COLUMNS)
    for col in target_columns:
        if col in out:
            out[col] = clean_text(out[col])
    return out


def mojibake_report(df: pd.DataFrame, columns: Iterable[str] | None = None) -> dict[str, int]:
    if df is None or df.empty:
        return {}
    report: dict[str, int] = {}
    target_columns = list(columns) if columns is not None else TEXT_COLUMNS
    for col in target_columns:
        if col not in df.columns:
            continue
        s = df[col].fillna("").astype(str)
        changed = s.apply(lambda x: clean_text(x) != x.strip())
        count = int(changed.sum())
        if count:
            report[col] = count
    return report
