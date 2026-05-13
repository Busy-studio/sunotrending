"""Tiny Streamlit custom component that bridges JS player localStorage to Python.

The main audio player still lives in app_modules.player_component as a plain
components.html iframe. This bridge is a separate lightweight component that
shares browser localStorage keys with the player and returns save/load events to
Streamlit/Python.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).parent / "frontend"
_component = components.declare_component("suno_playlist_bridge", path=str(_COMPONENT_DIR))


def suno_playlist_bridge(
    load_state: Optional[Dict[str, Any]] = None,
    load_request_id: str = "",
    key: str = "suno_playlist_bridge",
) -> Optional[Dict[str, Any]]:
    """Return a pending JS playlist event, or None.

    Args:
        load_state: Optional playlist state to write into the player localStorage
            before the player iframe restores itself.
        load_request_id: A unique id used so the frontend writes load_state only
            once per requested load.
    """

    return _component(
        loadState=load_state or None,
        loadRequestId=load_request_id or "",
        key=key,
        default=None,
    )
