from __future__ import annotations

import html
import json
import streamlit.components.v1 as components


def render_audio_tracker(song_id: str, audio_url: str, title: str, cover_url: str, public_config: dict, session_id: str, height: int = 92):
    if not audio_url:
        return
    payload = {
        "songId": song_id,
        "audioUrl": audio_url,
        "title": title or "Untitled",
        "coverUrl": cover_url or "",
        "supabaseUrl": public_config.get("supabase_url", ""),
        "anonKey": public_config.get("supabase_anon_key", ""),
        "sessionId": session_id,
    }
    js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    components.html(f"""
    <div class="bc-audio-box">
      <div class="bc-cover"><img src="{html.escape(cover_url or '')}" onerror="this.style.display='none'"></div>
      <div class="bc-main">
        <div class="bc-title">{html.escape(title or 'Untitled')}</div>
        <audio id="bc-audio" src="{html.escape(audio_url)}" preload="metadata" controls controlsList="nodownload" style="width:100%"></audio>
        <div id="bc-status" class="bc-status">30% 이상 재생 시 play count가 1회 반영됩니다.</div>
      </div>
    </div>
    <style>
      .bc-audio-box {{ display:flex; gap:12px; align-items:center; border:1px solid #e5e7eb; border-radius:16px; padding:10px; background:#fff; }}
      .bc-cover {{ width:64px; height:64px; border-radius:12px; overflow:hidden; background:#f3f4f6; flex:0 0 64px; }}
      .bc-cover img {{ width:100%; height:100%; object-fit:cover; display:block; }}
      .bc-main {{ flex:1; min-width:0; }}
      .bc-title {{ font-weight:900; font-size:14px; margin-bottom:5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
      .bc-status {{ font-size:11px; color:#6b7280; margin-top:3px; }}
    </style>
    <script>
      const cfg = {js};
      const audio = document.getElementById('bc-audio');
      const statusEl = document.getElementById('bc-status');
      let counted = false;
      async function recordPlay() {{
        if (counted || !cfg.supabaseUrl || !cfg.anonKey || !cfg.songId) return;
        counted = true;
        const seconds = Math.floor(audio.currentTime || 0);
        statusEl.textContent = 'play count 반영 중...';
        try {{
          const res = await fetch(cfg.supabaseUrl.replace(/\/$/, '') + '/rest/v1/rpc/bc_record_play', {{
            method: 'POST',
            headers: {{
              'content-type': 'application/json',
              'apikey': cfg.anonKey,
              'Authorization': 'Bearer ' + cfg.anonKey
            }},
            body: JSON.stringify({{ p_song_id: cfg.songId, p_session_id: cfg.sessionId, p_play_seconds: seconds }})
          }});
          statusEl.textContent = res.ok ? 'play count 반영됨' : 'play count 반영 실패';
        }} catch(e) {{
          statusEl.textContent = 'play count 반영 실패';
        }}
      }}
      audio.addEventListener('timeupdate', () => {{
        const dur = audio.duration || 0;
        if (!counted && dur > 0 && audio.currentTime / dur >= 0.30) recordPlay();
      }});
      audio.addEventListener('ended', () => {{ if (!counted) recordPlay(); }});
    </script>
    """, height=height)
