from __future__ import annotations

import html
import json
import streamlit.components.v1 as components


def render_audio_tracker(song_id: str, audio_url: str, title: str, cover_url: str, public_config: dict, session_id: str, height: int = 92, loudness_gain_db=None, integrated_lufs=None, true_peak_db=None):
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
        "loudnessGainDb": loudness_gain_db,
        "integratedLufs": integrated_lufs,
        "truePeakDb": true_peak_db,
    }
    js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    components.html(f"""
    <div class="bc-audio-box">
      <div class="bc-cover"><img src="{html.escape(cover_url or '')}" onerror="this.style.display='none'"></div>
      <div class="bc-main">
        <div class="bc-title">{html.escape(title or 'Untitled')}</div>
        <audio id="bc-audio" src="{html.escape(audio_url)}" preload="metadata" crossorigin="anonymous" controls controlsList="nodownload" style="width:100%"></audio>
        <div class="bc-loudness-row"><button id="bc-lufs-btn" class="bc-lufs-btn" type="button">-14 LUFS ON</button><span id="bc-lufs-info" class="bc-lufs-info"></span></div>
        <div id="bc-status" class="bc-status">30% 이상 재생 시 재생수가 반영됩니다.</div>
      </div>
    </div>
    <style>
      .bc-audio-box {{ display:flex; gap:12px; align-items:center; border:1px solid #e7ddd0; border-radius:18px; padding:10px; background:#fffdf8; box-shadow:0 8px 24px rgba(72,60,47,.055); }}
      .bc-cover {{ width:64px; height:64px; border-radius:12px; overflow:hidden; background:#f2ece2; flex:0 0 64px; }}
      .bc-cover img {{ width:100%; height:100%; object-fit:cover; display:block; }}
      .bc-main {{ flex:1; min-width:0; }}
      .bc-title {{ font-weight:900; font-size:14px; margin-bottom:5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
      .bc-status {{ font-size:11px; color:#7b7167; margin-top:3px; }}
      .bc-loudness-row {{ display:flex; align-items:center; gap:8px; margin:5px 0 2px; }}
      .bc-lufs-btn {{ border:1px solid #d9ccbb; background:#f7f1e7; color:#2f3a2f; border-radius:999px; padding:4px 10px; font-size:11px; font-weight:800; cursor:pointer; }}
      .bc-lufs-btn.off {{ color:#83786b; background:#fbf7ef; }}
      .bc-lufs-info {{ color:#7b7167; font-size:11px; }}
    </style>
    <script>
      const cfg = {js};
      const audio = document.getElementById('bc-audio');
      const statusEl = document.getElementById('bc-status');
      const lufsBtn = document.getElementById('bc-lufs-btn');
      const lufsInfo = document.getElementById('bc-lufs-info');
      let counted = false;
      let normalizeOn = true;
      let audioCtx = null;
      let gainNode = null;
      let sourceNode = null;
      function gainLinear() {{
        const db = Number(cfg.loudnessGainDb);
        if (!Number.isFinite(db)) return 1;
        return Math.max(0.05, Math.min(3.0, Math.pow(10, db / 20)));
      }}
      function updateLufsUi() {{
        const db = Number(cfg.loudnessGainDb);
        if (!Number.isFinite(db)) {{
          lufsBtn.textContent = '-14 LUFS N/A';
          lufsBtn.disabled = true;
          lufsInfo.textContent = '분석 없음';
          return;
        }}
        lufsBtn.textContent = normalizeOn ? '-14 LUFS ON' : '-14 LUFS OFF';
        lufsBtn.className = normalizeOn ? 'bc-lufs-btn' : 'bc-lufs-btn off';
        const lufs = Number(cfg.integratedLufs);
        const gainText = `${{db >= 0 ? '+' : ''}}${{db.toFixed(1)}} dB`;
        lufsInfo.textContent = Number.isFinite(lufs) ? `${{lufs.toFixed(1)}} LUFS · ${{gainText}}` : gainText;
        if (gainNode) gainNode.gain.value = normalizeOn ? gainLinear() : 1;
        else audio.volume = normalizeOn ? Math.min(1, gainLinear()) : 1;
      }}
      function initAudioGraph() {{
        if (audioCtx || !normalizeOn) return;
        try {{
          audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          sourceNode = audioCtx.createMediaElementSource(audio);
          gainNode = audioCtx.createGain();
          gainNode.gain.value = gainLinear();
          sourceNode.connect(gainNode).connect(audioCtx.destination);
        }} catch(e) {{
          audio.volume = Math.min(1, gainLinear());
        }}
      }}
      lufsBtn.addEventListener('click', () => {{ normalizeOn = !normalizeOn; updateLufsUi(); }});
      audio.addEventListener('play', () => {{ initAudioGraph(); if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume(); updateLufsUi(); }});
      updateLufsUi();
      async function recordPlay() {{
        if (counted || !cfg.supabaseUrl || !cfg.anonKey || !cfg.songId) return;
        counted = true;
        const seconds = Math.floor(audio.currentTime || 0);
        statusEl.textContent = '재생수 반영 중...';
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
          statusEl.textContent = res.ok ? '재생수 반영됨' : '재생수 반영 실패';
        }} catch(e) {{
          statusEl.textContent = '재생수 반영 실패';
        }}
      }}
      audio.addEventListener('timeupdate', () => {{
        const dur = audio.duration || 0;
        if (!counted && dur > 0 && audio.currentTime / dur >= 0.30) recordPlay();
      }});
      audio.addEventListener('ended', () => {{ if (!counted) recordPlay(); }});
    </script>
    """, height=height)
