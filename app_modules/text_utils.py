"""Streamlit app text and value normalization helpers."""

import pandas as pd

try:
    import ftfy
except Exception:
    ftfy = None


def broken_score(s: str) -> int:
    if not s:
        return 999999

    bad_markers = [
        "Ã", "ã", "Â", "â", "ð", "Ð", "Ñ", "Î", "Ï",
        "ç", "è", "é", "ê", "ë", "í", "ì", "Å", " ",
    ]

    score = sum(s.count(ch) * 3 for ch in bad_markers)
    score += sum(5 for ch in s if 0x80 <= ord(ch) <= 0x9F)
    score += max(0, 8 - len(s))

    return score


def try_decode_utf8_from_latinish(s: str):
    candidates = []

    for enc in ["latin1", "cp1252"]:
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


def fix_mojibake(value):
    if pd.isna(value):
        return ""

    original = str(value)

    if not original:
        return ""

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
        new_frontier = []

        for s in frontier:
            for fixed in try_decode_utf8_from_latinish(s):
                if fixed and fixed not in candidates:
                    candidates.append(fixed)
                    new_frontier.append(fixed)

            if ftfy is not None:
                try:
                    fixed = ftfy.fix_text(s)
                    if fixed and fixed not in candidates:
                        candidates.append(fixed)
                        new_frontier.append(fixed)
                except Exception:
                    pass

        frontier = new_frontier

        if not frontier:
            break

    return min(candidates, key=broken_score)


def safe_text(value):
    if pd.isna(value):
        return ""

    s = fix_mojibake(value).strip()

    if s.lower() in ["nan", "none"]:
        return ""

    return s


def is_fake_rsc_token(value):
    s = safe_text(value)

    if not s:
        return True

    if s.startswith("$") and len(s) <= 8:
        return True

    return False


def safe_url(value):
    if pd.isna(value):
        return ""

    s = str(value).strip()

    if s.lower() in ["nan", "none", ""]:
        return ""

    return s

def safe_float_or_none(value):
    try:
        if pd.isna(value):
            return None

        s = str(value).strip()

        if s.lower() in ["", "nan", "none", "<na>", "null", "-"]:
            return None

        return float(s)
    except Exception:
        return None


def safe_int_or_none(value):
    try:
        f = safe_float_or_none(value)

        if f is None:
            return None

        return int(f)
    except Exception:
        return None


def normalize_handle(value):
    handle = safe_text(value)

    if not handle:
        return ""

    if handle.startswith("@"):
        handle = handle[1:]

    return handle


def build_creator_display(display_name_value, handle_value):
    display_name = safe_text(display_name_value)
    handle = normalize_handle(handle_value)

    primary = display_name or handle or "-"
    secondary = f"@{handle}" if handle else ""

    return primary, secondary


