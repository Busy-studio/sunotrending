"""Load prebuilt chart payloads from Supabase.

This replaces the old data-branch ZIP payload path when public.app_payloads has a
row with key='latest'. The old ZIP loader remains as a fallback in app.py.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

import streamlit as st

from app_modules.supabase_store import get_supabase_client


@st.cache_data(ttl=60, show_spinner=False)
def load_supabase_app_payload(cache_key: str = "latest") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (payload, error) from public.app_payloads.

    Supports both direct CSV import schema where payload_json is text and future
    typed schema where payload_json may be json/jsonb and arrives as dict.
    """
    sb = get_supabase_client()
    if not sb:
        return None, "Supabase client is not configured"

    try:
        result = (
            sb.table("app_payloads")
            .select("key,payload_json,updated_at")
            .eq("key", cache_key)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        return None, f"Supabase app_payloads read failed: {exc}"

    rows = result.data or []
    if not rows:
        return None, "Supabase app_payloads.latest row not found"

    raw_payload = rows[0].get("payload_json")
    if isinstance(raw_payload, dict):
        payload = raw_payload
    elif isinstance(raw_payload, str):
        raw_payload = raw_payload.strip()
        if not raw_payload:
            return None, "Supabase app_payloads.latest payload_json is empty"
        try:
            payload = json.loads(raw_payload)
        except Exception as exc:
            return None, f"Supabase app_payloads.latest JSON parse failed: {exc}"
    else:
        return None, f"Unsupported payload_json type: {type(raw_payload).__name__}"

    if not isinstance(payload, dict):
        return None, "Supabase app_payloads.latest is not an object"

    payload.setdefault("meta", {})
    if isinstance(payload.get("meta"), dict):
        payload["meta"].setdefault("supabase_payload_updated_at", rows[0].get("updated_at"))

    return payload, None
