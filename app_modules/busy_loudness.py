from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Dict, Optional

TARGET_LUFS = -14.0
TRUE_PEAK_CEILING_DB = -1.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def analyze_audio_loudness(uploaded_file) -> Dict[str, Any]:
    """Best-effort upload-time loudness analysis.

    Uses soundfile + pyloudnorm when available. If the host cannot decode the
    uploaded MP3, we keep the upload working and mark loudness_status=skipped.
    Playback still works; normalization button/status simply stays unavailable.
    """
    result: Dict[str, Any] = {
        "integrated_lufs": None,
        "true_peak_db": None,
        "loudness_gain_db": None,
        "loudness_target_lufs": TARGET_LUFS,
        "loudness_true_peak_ceiling_db": TRUE_PEAK_CEILING_DB,
        "loudness_checked_at": _now_iso(),
        "loudness_status": "skipped",
        "loudness_error": "",
    }
    if uploaded_file is None:
        result["loudness_error"] = "no_file"
        return result
    try:
        import numpy as np
        import soundfile as sf
        import pyloudnorm as pyln
    except Exception as exc:
        result["loudness_error"] = f"loudness_deps_missing: {exc}"
        return result

    try:
        data = uploaded_file.getvalue()
        with sf.SoundFile(io.BytesIO(data)) as f:
            sr = int(f.samplerate)
            # Avoid loading extremely long files in one chunk. Prototype policy is MP3 <= 25MB,
            # but cap analysis to 10 minutes just in case.
            max_frames = min(len(f), sr * 60 * 10)
            audio = f.read(frames=max_frames, dtype="float32", always_2d=True)
        if audio.size == 0:
            result["loudness_error"] = "empty_audio"
            return result
        meter = pyln.Meter(sr)
        integrated = float(meter.integrated_loudness(audio))
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        true_peak_db = float(20.0 * np.log10(max(peak, 1e-12)))
        gain = TARGET_LUFS - integrated
        # Conservative ceiling protection. If applying the gain would exceed -1 dBTP,
        # reduce gain. This mirrors the old -14 LUFS / -1 dB ceiling intent.
        if true_peak_db + gain > TRUE_PEAK_CEILING_DB:
            gain = TRUE_PEAK_CEILING_DB - true_peak_db
        result.update({
            "integrated_lufs": round(integrated, 2),
            "true_peak_db": round(true_peak_db, 2),
            "loudness_gain_db": round(float(gain), 2),
            "loudness_status": "ok",
            "loudness_error": "",
        })
        return result
    except Exception as exc:
        result["loudness_error"] = str(exc)[:500]
        return result
