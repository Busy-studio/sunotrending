"""HTML/JavaScript audio player and ranking table component."""

import base64
import html
import json

import streamlit.components.v1 as components

from app_modules.text_utils import safe_text as _safe_text


def clean_payload_text(value):
    return _safe_text(value)


def render_player_ranking_html(
    songs_json,
    histories_json,
    ranking_config_json,
    title="Top 200",
    subtitle=None,
    tabs_json="null",
    tabs_order_json="[]",
    default_tab_key="",
    cloud_config_json="{}",
):
    title = clean_payload_text(title) or "Suno Songs"
    subtitle = clean_payload_text(subtitle) or "앨범 이미지를 누르면 해당 곡을 재생 또는 일시정지합니다."
    title_html = html.escape(title)
    subtitle_html = html.escape(subtitle)
    default_tab_key_js = json.dumps(default_tab_key or "", ensure_ascii=False)

    try:
        _cloud_cfg_for_layout = json.loads(cloud_config_json or "{}")
    except Exception:
        _cloud_cfg_for_layout = {}
    shell_extra_class = "" if _cloud_cfg_for_layout.get("playerEnabled") else " public-mode"

    html_template = """
    <style>
    :root {
        --bg: #ffffff;
        --panel: #f8fafc;
        --line: #e5e7eb;
        --line-dark: #d1d5db;
        --text: #111827;
        --muted: #6b7280;
        --accent: #ef4444;
        --accent-dark: #dc2626;
        --soft: #f3f4f6;
    }

    * { box-sizing: border-box; }

    html, body {
        margin: 0;
        padding: 0;
        background: var(--bg);
        color: var(--text);
        font-family:
            "Noto Sans KR", "Noto Sans", "Apple SD Gothic Neo",
            "Malgun Gothic", "Segoe UI", Arial, sans-serif;
    }

    .app-shell {
        display: grid;
        grid-template-columns: 330px minmax(720px, 1fr);
        gap: 16px;
        width: 100%;
        height: 1200px;
        min-height: 0;
        align-items: stretch;
    }

    .app-shell.public-mode {
        grid-template-columns: minmax(720px, 1fr);
    }

    .app-shell.public-mode .player-panel {
        display: none;
    }

    .player-panel {
        position: sticky;
        top: 0;
        align-self: stretch;
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 14px;
        height: 100%;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        min-height: 0;
    }

    .now-cover-wrap {
        width: 100%;
        aspect-ratio: 1 / 1;
        border-radius: 18px;
        overflow: hidden;
        background: #e5e7eb;
        margin-bottom: 12px;
        position: relative;
    }

    .now-cover {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }

    .now-placeholder {
        width: 100%;
        height: 100%;
        display: grid;
        place-items: center;
        color: var(--muted);
        font-size: 13px;
    }

    .now-title {
        font-size: 18px;
        font-weight: 850;
        line-height: 1.25;
        margin-bottom: 4px;
        word-break: break-word;
    }

    .now-creator {
        font-size: 13px;
        color: var(--muted);
        margin-bottom: 7px;
        word-break: break-word;
    }

    .now-style-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin: 0 0 10px 0;
        min-height: 20px;
    }

    .now-style-tag {
        display: inline-block;
        max-width: 125px;
        border: 1px solid var(--line);
        background: #ffffff;
        color: #374151;
        border-radius: 999px;
        padding: 3px 8px;
        font-size: 11px;
        line-height: 1.2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .now-style-empty {
        color: var(--muted);
        font-size: 12px;
    }

    .lyrics-panel {
        margin-top: 10px;
        border: 1px solid var(--line);
        background: #ffffff;
        border-radius: 12px;
        padding: 10px;
        height: 210px;
        overflow-y: auto;
        white-space: pre-wrap;
        font-size: 12px;
        line-height: 1.45;
        color: #374151;
    }

    .lyrics-panel.empty { color: var(--muted); }

    .progress-wrap { margin: 10px 0 8px 0; }

    .time-row {
        display: flex;
        justify-content: space-between;
        color: var(--muted);
        font-size: 11px;
        margin-top: 4px;
    }

    input[type="range"] {
        width: 100%;
        accent-color: var(--accent);
    }

    .control-row {
        display: flex;
        gap: 8px;
        align-items: center;
        justify-content: center;
        margin: 10px 0;
    }

    .ctrl-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 999px;
        min-width: 38px;
        height: 38px;
        cursor: pointer;
        font-weight: 800;
        font-size: 14px;
    }

    .ctrl-btn.main {
        background: var(--accent);
        color: white;
        border-color: var(--accent);
        min-width: 46px;
        height: 46px;
        font-size: 16px;
    }

    .ctrl-btn:hover { border-color: var(--accent); }

    .rank-change {
        text-align: center;
        white-space: nowrap;
        font-size: 12px;
        font-weight: 900;
        font-variant-numeric: tabular-nums;
    }

    .rank-up {
        color: #dc2626;
    }

    .rank-down {
        color: #2563eb;
    }

    .rank-new {
        color: #16a34a;
        font-weight: 950;
        letter-spacing: 0.02em;
    }

    .rank-same {
        color: var(--muted);
    }

    .mode-actions {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 6px;
        margin-bottom: 12px;
    }

    .small-btn {
        border: 1px solid var(--line-dark);
        background: white;
        color: var(--text);
        border-radius: 10px;
        padding: 8px 4px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 800;
        white-space: nowrap;
    }

    .small-btn.active {
        background: #fee2e2;
        color: var(--accent-dark);
        border-color: var(--accent);
    }

    .volume-row {
        display: grid;
        grid-template-columns: 54px 1fr 42px;
        gap: 8px;
        align-items: center;
        font-size: 12px;
        color: var(--muted);
        margin: 8px 0 12px 0;
    }

    .loudness-row {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 8px;
        align-items: center;
        font-size: 11px;
        color: var(--muted);
        margin: -4px 0 12px 0;
    }

    .loudness-status {
        min-width: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .loudness-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 999px;
        padding: 6px 9px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 850;
        white-space: nowrap;
    }

    .loudness-btn.active {
        background: #fee2e2;
        color: var(--accent-dark);
        border-color: var(--accent);
    }

    .cloud-playlist-box {
        border: 1px solid var(--line);
        background: #ffffff;
        border-radius: 12px;
        padding: 10px;
        margin: 10px 0 12px 0;
    }

    .cloud-playlist-title {
        font-size: 12px;
        font-weight: 900;
        margin-bottom: 7px;
        color: var(--text);
    }

    .cloud-playlist-row {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 6px;
        align-items: center;
    }

    .cloud-playlist-input {
        min-width: 0;
        border: 1px solid var(--line-dark);
        border-radius: 999px;
        padding: 8px 10px;
        font-size: 12px;
        outline: none;
    }

    .cloud-playlist-input:focus { border-color: var(--accent); }

    .cloud-playlist-save {
        border: 1px solid var(--accent);
        background: var(--accent);
        color: #ffffff;
        border-radius: 999px;
        padding: 8px 10px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 900;
        white-space: nowrap;
    }

    .cloud-playlist-save:disabled {
        background: #f3f4f6;
        color: var(--muted);
        border-color: var(--line-dark);
        cursor: not-allowed;
    }

    .cloud-playlist-status {
        margin-top: 6px;
        color: var(--muted);
        font-size: 11px;
        line-height: 1.35;
        min-height: 15px;
    }

    .cloud-playlist-manage {
        display: grid;
        grid-template-columns: 1fr auto auto;
        gap: 6px;
        align-items: center;
        margin-top: 8px;
    }

    .cloud-playlist-select {
        min-width: 0;
        border: 1px solid var(--line-dark);
        border-radius: 999px;
        padding: 8px 10px;
        font-size: 12px;
        background: #ffffff;
        outline: none;
    }

    .cloud-playlist-mini-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 999px;
        padding: 8px 9px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 850;
        white-space: nowrap;
    }

    .cloud-playlist-mini-btn:hover { border-color: var(--accent); color: var(--accent); }
    .cloud-playlist-mini-btn:disabled { color: var(--muted); background: #f3f4f6; cursor: not-allowed; }

    .playlist-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 12px 0 8px 0;
    }

    .playlist-title {
        font-size: 14px;
        font-weight: 850;
    }

    .playlist-count {
        font-size: 12px;
        color: var(--muted);
    }

    .playlist {
        border: 1px solid var(--line);
        background: #ffffff;
        border-radius: 12px;
        overflow-y: auto;
        height: 260px;
    }

    .playlist-empty {
        color: var(--muted);
        font-size: 12px;
        padding: 14px;
        line-height: 1.5;
    }

    .playlist-item {
        display: grid;
        grid-template-columns: 34px 1fr 28px;
        gap: 8px;
        align-items: center;
        padding: 8px;
        border-bottom: 1px solid var(--line);
        cursor: pointer;
    }

    .playlist-item:last-child { border-bottom: 0; }
    .playlist-item.active { background: #fee2e2; }

    .playlist-thumb {
        width: 34px;
        height: 34px;
        border-radius: 8px;
        object-fit: cover;
        background: #e5e7eb;
    }

    .playlist-meta {
        overflow: hidden;
        min-width: 0;
    }

    .playlist-song-title {
        font-size: 12px;
        font-weight: 800;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .playlist-song-sub {
        font-size: 11px;
        color: var(--muted);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .remove-btn {
        border: 0;
        background: transparent;
        color: var(--muted);
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
    }

    .ranking-panel {
        min-width: 0;
        border: 1px solid var(--line);
        border-radius: 18px;
        overflow: hidden;
        background: #ffffff;
        height: 100%;
        display: flex;
        flex-direction: column;
        min-height: 0;
    }

    .ranking-topbar {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
        padding: 12px;
        background: #ffffff;
        border-bottom: 1px solid var(--line);
    }

    .rank-view-tabs {
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
        margin-bottom: 8px;
    }

    .rank-view-tab {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--muted);
        border-radius: 999px;
        padding: 7px 12px;
        font-size: 12px;
        font-weight: 900;
        cursor: pointer;
        transition: all 0.15s ease;
    }

    .rank-view-tab:hover {
        border-color: var(--accent);
        color: var(--accent);
    }

    .rank-view-tab.active {
        background: var(--accent);
        border-color: var(--accent);
        color: #ffffff;
    }

    .ranking-title {
        font-size: 16px;
        font-weight: 900;
    }

    .ranking-sub {
        color: var(--muted);
        font-size: 12px;
        margin-top: 2px;
    }

    .search-input {
        border: 1px solid var(--line-dark);
        border-radius: 999px;
        padding: 9px 13px;
        min-width: 260px;
        outline: none;
    }

    .search-input:focus { border-color: var(--accent); }

    .table-wrap {
        width: 100%;
        overflow-x: auto;
        overflow-y: auto;
        flex: 1;
        min-height: 0;
    }

    .app-shell.public-mode .select-col,
    .app-shell.public-mode .select-cell {
        display: none;
    }

    table.song-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        table-layout: fixed;
        color: var(--text);
    }

    .song-table th {
        text-align: left;
        padding: 11px 8px;
        border-bottom: 1px solid var(--line-dark);
        background: var(--soft);
        position: sticky;
        top: 0;
        z-index: 2;
        font-weight: 800;
        color: var(--text);
    }

    .song-table td {
        padding: 8px;
        border-bottom: 1px solid var(--line);
        vertical-align: middle;
        color: var(--text);
    }

    .song-table tr:hover { background: #f9fafb; }

    .song-table tr.outlier-row {
        background: #fff7ed;
    }

    .song-table tr.outlier-row:hover {
        background: #ffedd5;
    }

    .outlier-badge {
        display: inline-block;
        margin-left: 6px;
        border: 1px solid #f97316;
        background: #fed7aa;
        color: #9a3412;
        border-radius: 999px;
        padding: 2px 6px;
        font-size: 10px;
        font-weight: 900;
        vertical-align: middle;
        white-space: nowrap;
    }

    .select-cell { text-align: center; }

    .rank {
        font-weight: 850;
        font-size: 16px;
        text-align: right;
    }

    .cover-cell {
        display: flex;
        align-items: center;
    }

    .cover-btn {
        border: 0;
        padding: 0;
        margin: 0;
        background: transparent;
        cursor: pointer;
        position: relative;
        width: 56px;
        height: 56px;
        display: block;
        flex-shrink: 0;
    }

    .cover {
        width: 56px;
        height: 56px;
        object-fit: cover;
        border-radius: 10px;
        background: #e5e7eb;
        display: block;
    }

    .cover-btn::after {
        content: "▶";
        position: absolute;
        right: 4px;
        bottom: 4px;
        width: 20px;
        height: 20px;
        border-radius: 999px;
        background: rgba(0,0,0,0.72);
        color: white;
        font-size: 11px;
        line-height: 20px;
        text-align: center;
        font-weight: 800;
    }

    .cover-btn.playing::after {
        content: "Ⅱ";
        background: var(--accent);
    }

    .cover-btn.paused::after {
        content: "▶";
        background: var(--accent);
    }

    .add-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 8px;
        width: 32px;
        height: 32px;
        cursor: pointer;
        font-weight: 900;
    }

    .add-btn.added {
        color: white;
        background: var(--accent);
        border-color: var(--accent);
    }

    .title-cell {
        overflow: hidden;
        word-break: break-word;
        color: var(--text);
    }

    .title-link {
        font-weight: 850;
        text-decoration: none;
        color: var(--text);
        display: inline-block;
        max-width: 100%;
        white-space: normal;
        line-height: 1.35;
    }

    .title-link:hover {
        text-decoration: underline;
        color: var(--accent);
    }

    .style-cell {
        overflow: hidden;
        white-space: nowrap;
    }

    .style-tags {
        display: flex;
        flex-wrap: nowrap;
        gap: 4px;
        align-items: center;
        overflow: hidden;
        max-width: 100%;
    }

    .style-tag {
        display: inline-block;
        flex: 0 1 auto;
        min-width: 0;
        max-width: 84px;
        border: 1px solid var(--line);
        background: #f9fafb;
        color: #374151;
        border-radius: 999px;
        padding: 3px 7px;
        font-size: 11px;
        line-height: 1.2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .style-empty {
        color: var(--muted);
        font-size: 12px;
    }

    .subtle {
        color: var(--muted);
        font-size: 12px;
        margin-top: 4px;
        line-height: 1.25;
    }

    .creator {
        line-height: 1.35;
        word-break: break-word;
        color: var(--text);
    }

    .creator-link {
        color: inherit;
        text-decoration: none;
        font-weight: 750;
    }

    .creator-link:hover {
        color: var(--accent-dark);
        text-decoration: underline;
    }

    .num {
        text-align: right;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
        color: var(--text);
    }

    .rank-info-btn {
        border: 1px solid var(--line-dark);
        background: #ffffff;
        color: var(--text);
        border-radius: 999px;
        padding: 6px 10px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 800;
        white-space: nowrap;
    }

    .rank-info-btn:hover {
        border-color: var(--accent);
        color: var(--accent-dark);
    }

    .modal-backdrop {
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.45);
        z-index: 9999;
        padding: 28px;
        overflow-y: auto;
    }

    .modal-backdrop.open { display: block; }

    .modal-card {
        background: white;
        color: var(--text);
        border-radius: 18px;
        max-width: 780px;
        margin: 0 auto;
        padding: 18px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.25);
    }

    .modal-head {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: start;
        margin-bottom: 12px;
    }

    .modal-title {
        font-size: 18px;
        font-weight: 900;
        line-height: 1.3;
    }

    .modal-sub {
        color: var(--muted);
        font-size: 12px;
        margin-top: 4px;
    }

    .modal-close {
        border: 1px solid var(--line-dark);
        background: white;
        border-radius: 999px;
        cursor: pointer;
        width: 34px;
        height: 34px;
        font-weight: 900;
    }

    .score-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin: 12px 0;
    }

    .score-box {
        border: 1px solid var(--line);
        background: var(--panel);
        border-radius: 12px;
        padding: 10px;
    }

    .score-label {
        color: var(--muted);
        font-size: 11px;
        margin-bottom: 4px;
    }

    .score-value {
        font-size: 17px;
        font-weight: 900;
        font-variant-numeric: tabular-nums;
    }

    .song-table th.sortable {
        cursor: pointer;
        user-select: none;
    }

    .song-table th.sortable:hover {
        color: var(--accent-dark);
    }

    .sort-indicator {
        margin-left: 4px;
        font-size: 10px;
        color: var(--muted);
    }

    .chart-wrap {
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 10px;
        overflow-x: auto;
    }

    .footer-credit {
        margin-top: 16px;
        padding: 16px;
        text-align: center;
        color: var(--muted);
        font-size: 12px;
    }

    .footer-credit a {
        color: var(--accent-dark);
        font-weight: 900;
        text-decoration: none;
    }

    .footer-credit a:hover { text-decoration: underline; }

    @media (max-width: 980px) {
        .app-shell {
            grid-template-columns: 1fr;
            height: auto;
            min-height: 0;
        }

        .player-panel {
            position: relative;
            height: 1180px;
            max-height: none;
        }

        .playlist { min-height: 180px; }
        .lyrics-panel { height: 180px; }
        .score-grid { grid-template-columns: repeat(2, 1fr); }
    }
    </style>

    <div class="app-shell{shell_extra_class}" id="appShell">
        <aside class="player-panel">
            <div class="now-cover-wrap" id="nowCoverWrap">
                <div class="now-placeholder">No track selected</div>
            </div>

            <div class="now-title" id="nowTitle">플레이리스트에 곡을 추가하세요</div>
            <div class="now-creator" id="nowCreator">앨범 이미지나 체크 버튼을 누르면 추가됩니다.</div>
            <div class="now-style-tags" id="nowStyleTags"></div>

            <div class="lyrics-panel empty" id="lyricsPanel">가사/프롬프트 정보가 있으면 여기에 표시됩니다.</div>

            <div class="progress-wrap">
                <input id="progress" type="range" min="0" max="1000" value="0">
                <div class="time-row">
                    <span id="currentTime">0:00</span>
                    <span id="duration">0:00</span>
                </div>
            </div>

            <div class="control-row">
                <button class="ctrl-btn" id="prevBtn" title="이전 곡">⏮</button>
                <button class="ctrl-btn main" id="playBtn" title="재생 / 일시정지">▶</button>
                <button class="ctrl-btn" id="nextBtn" title="다음 곡">⏭</button>
            </div>

            <div class="mode-actions">
                <button class="small-btn" id="repeatOneBtn">한곡 반복</button>
                <button class="small-btn active" id="repeatAllBtn">전체 반복</button>
                <button class="small-btn active" id="sequenceBtn">순차 재생</button>
                <button class="small-btn" id="shuffleBtn">랜덤 재생</button>
                <button class="small-btn" id="clearBtn">초기화</button>
            </div>

            <div class="volume-row">
                <span>Volume</span>
                <input id="volume" type="range" min="0" max="100" value="80">
                <span id="volumeText">80%</span>
            </div>

            <div class="loudness-row">
                <span class="loudness-status" id="loudnessStatus">LUFS 정규화 꺼짐</span>
                <button class="loudness-btn" id="loudnessNormalizeBtn" title="분석된 LUFS/True Peak 값으로 -14 LUFS 기준 재생 볼륨을 보정합니다.">-14 LUFS OFF</button>
            </div>

            <div class="cloud-playlist-box">
                <div class="cloud-playlist-title">Cloud Playlist</div>
                <div class="cloud-playlist-row">
                    <input class="cloud-playlist-input" id="cloudPlaylistName" placeholder="저장할 플레이리스트 이름">
                    <button class="cloud-playlist-save" id="cloudSavePlaylistBtn">저장</button>
                </div>
                <div class="cloud-playlist-manage">
                    <select class="cloud-playlist-select" id="cloudPlaylistSelect">
                        <option value="">저장된 플레이리스트</option>
                    </select>
                    <button class="cloud-playlist-mini-btn" id="cloudLoadPlaylistBtn">불러오기</button>
                    <button class="cloud-playlist-mini-btn" id="cloudDeletePlaylistBtn">삭제</button>
                </div>
                <div class="cloud-playlist-status" id="cloudPlaylistStatus">로그인 후 현재 JS 플레이리스트를 서버에 저장할 수 있습니다.</div>
            </div>

            <div class="playlist-head">
                <div class="playlist-title">Playlist</div>
                <div class="playlist-count" id="playlistCount">0 tracks</div>
            </div>

            <div class="playlist" id="playlist">
                <div class="playlist-empty">
                    아직 플레이리스트가 비어 있습니다.<br>
                    오른쪽 랭킹에서 앨범 이미지나 체크 버튼을 눌러 추가하세요.
                </div>
            </div>
        </aside>

        <main class="ranking-panel">
            <div class="ranking-topbar">
                <div>
                    <div class="rank-view-tabs" id="rankViewTabs"></div>
                    <div class="ranking-title" id="rankingTitle">{title_html}</div>
                    <div class="ranking-sub" id="rankingSub">{subtitle_html}</div>
                </div>
                <input class="search-input" id="searchInput" placeholder="Search title / style / creator / handle">
            </div>

            <div class="table-wrap">
                <table class="song-table">
                    <thead>
                        <tr>
                            <th class="select-col" style="width:46px; text-align:center;">선택</th>
                            <th class="sortable" data-sort-key="rank" style="width:42px; text-align:right;">순위<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="rank_change" style="width:58px; text-align:center;">변동<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="has_image" style="width:76px;">앨범<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="title" style="width:360px;">곡 제목<span class="sort-indicator"></span></th>
                            <th style="width:170px;">스타일</th>
                            <th class="sortable" data-sort-key="creator" style="width:210px;">창작자<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="play_count" style="width:76px; text-align:right;">플레이<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="upvote_count" style="width:76px; text-align:right;">좋아요<span class="sort-indicator"></span></th>
                            <th class="sortable" data-sort-key="comment_count" style="width:64px; text-align:right;">댓글<span class="sort-indicator"></span></th>
                            <th style="width:90px; text-align:center;">상세정보</th>
                        </tr>
                    </thead>
                    <tbody id="songTableBody"></tbody>
                </table>
            </div>

            <div class="footer-credit">
                This page was created by
                <a href="https://suno.com/@busystudio" target="_blank" rel="noopener noreferrer">Busy Studio</a>.
            </div>
        </main>
    </div>

    <div class="modal-backdrop" id="rankingModal">
        <div class="modal-card">
            <div class="modal-head">
                <div>
                    <div class="modal-title" id="modalTitle">Detailed Info</div>
                    <div class="modal-sub" id="modalSub"></div>
                </div>
                <button class="modal-close" id="modalCloseBtn">×</button>
            </div>

            <div class="score-grid">
                <div class="score-box">
                    <div class="score-label">Trend Score</div>
                    <div class="score-value" id="scoreTrend">0</div>
                </div>
                <div class="score-box">
                    <div class="score-label">Base</div>
                    <div class="score-value" id="scoreBase">0</div>
                </div>
                <div class="score-box">
                    <div class="score-label">Growth</div>
                    <div class="score-value" id="scoreGrowth">0</div>
                </div>
                <div class="score-box">
                    <div class="score-label">Freshness</div>
                    <div class="score-value" id="scoreFreshness">0</div>
                </div>
            </div>

            <div class="chart-wrap">
                <canvas id="historyCanvas" width="720" height="260"></canvas>
            </div>
        </div>
    </div>

    <script>
    function decodeB64Json(b64, fallbackValue) {
        try {
            if (!b64) return fallbackValue;
            const binary = atob(b64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i += 1) {
                bytes[i] = binary.charCodeAt(i);
            }
            return JSON.parse(new TextDecoder("utf-8").decode(bytes));
        } catch (error) {
            console.error("Failed to decode embedded JSON", error);
            return fallbackValue;
        }
    }

    let songs = decodeB64Json("__SONGS_JSON_B64__", []);
    let histories = decodeB64Json("__HISTORIES_JSON_B64__", {});
    const rankingConfig = decodeB64Json("__RANKING_CONFIG_JSON_B64__", {});
    const tabsData = decodeB64Json("__TABS_JSON_B64__", null);
    const tabsOrder = decodeB64Json("__TABS_ORDER_JSON_B64__", []);
    const defaultTabKey = __DEFAULT_TAB_KEY__;
    const cloudConfig = decodeB64Json("__CLOUD_CONFIG_JSON_B64__", {});
    const playerEnabled = Boolean(cloudConfig && cloudConfig.playerEnabled);

    const playlistStorageKey = "sunoTrending.playlist.v1";
    const cloudLoadRequestStorageKey = "sunoTrending.cloudLoad.request.v1";

    let playlist = [];
    let currentIndex = -1;
    let audio = new Audio();
    let audioContext = null;
    let audioSourceNode = null;
    let loudnessGainNode = null;
    let webAudioReady = false;
    let webAudioFailed = false;
    let loudnessNormalize = false;
    let suppressStateSave = false;
    let lastStateSaveAt = 0;
    let lastCloudLoadRequestId = "";

    let repeatOne = false;
    let repeatAll = true;
    let playbackMode = "sequence";

    let sortState = {
        key: null,
        direction: null,
    };

    const nowCoverWrap = document.getElementById("nowCoverWrap");
    const nowTitle = document.getElementById("nowTitle");
    const nowCreator = document.getElementById("nowCreator");
    const nowStyleTags = document.getElementById("nowStyleTags");
    const playlistEl = document.getElementById("playlist");
    const playlistCount = document.getElementById("playlistCount");
    const lyricsPanel = document.getElementById("lyricsPanel");

    const playBtn = document.getElementById("playBtn");
    const prevBtn = document.getElementById("prevBtn");
    const nextBtn = document.getElementById("nextBtn");
    const repeatOneBtn = document.getElementById("repeatOneBtn");
    const repeatAllBtn = document.getElementById("repeatAllBtn");
    const sequenceBtn = document.getElementById("sequenceBtn");
    const shuffleBtn = document.getElementById("shuffleBtn");
    const clearBtn = document.getElementById("clearBtn");
    const volume = document.getElementById("volume");
    const volumeText = document.getElementById("volumeText");
    const loudnessNormalizeBtn = document.getElementById("loudnessNormalizeBtn");
    const loudnessStatus = document.getElementById("loudnessStatus");
    const cloudPlaylistName = document.getElementById("cloudPlaylistName");
    const cloudSavePlaylistBtn = document.getElementById("cloudSavePlaylistBtn");
    const cloudPlaylistSelect = document.getElementById("cloudPlaylistSelect");
    const cloudLoadPlaylistBtn = document.getElementById("cloudLoadPlaylistBtn");
    const cloudDeletePlaylistBtn = document.getElementById("cloudDeletePlaylistBtn");
    const cloudPlaylistStatus = document.getElementById("cloudPlaylistStatus");
    const progress = document.getElementById("progress");
    const currentTimeEl = document.getElementById("currentTime");
    const durationEl = document.getElementById("duration");
    const searchInput = document.getElementById("searchInput");
    const rankViewTabs = document.getElementById("rankViewTabs");
    const rankingTitle = document.getElementById("rankingTitle");
    const rankingSub = document.getElementById("rankingSub");
    const songTableBody = document.getElementById("songTableBody");

    const rankingModal = document.getElementById("rankingModal");
    const modalCloseBtn = document.getElementById("modalCloseBtn");
    const modalTitle = document.getElementById("modalTitle");
    const modalSub = document.getElementById("modalSub");
    const scoreTrend = document.getElementById("scoreTrend");
    const scoreBase = document.getElementById("scoreBase");
    const scoreGrowth = document.getElementById("scoreGrowth");
    const scoreFreshness = document.getElementById("scoreFreshness");
    const historyCanvas = document.getElementById("historyCanvas");

    function escapeHtml(text) {
        if (text === null || text === undefined) return "";

        return String(text)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function creatorProfileUrl(song) {
        const rawHandle = String(song.handle || "").trim();
        const handle = rawHandle.replace(/^@+/, "").trim();
        if (!handle || handle === "-") return "";
        return `https://suno.com/@${encodeURIComponent(handle)}`;
    }

    const TAB_LABEL_FALLBACKS = {
        "new_songs": "New Song",
        "top200": "Top 200",
        "rain_crew": "☔rain crew",
    };

    const TAB_DESCRIPTION_FALLBACKS = {
        "new_songs": "생성일 기준 최신순",
        "top200": "현재 날짜 기준 4일 이내 전체 DB 곡 중 trend_score 상위 200",
        "rain_crew": "☔rain crew 멤버 곡 최신순",
    };

    function prettifyTabKey(key) {
        return String(key || "")
            .split("_")
            .filter(Boolean)
            .map(part => part.charAt(0).toUpperCase() + part.slice(1))
            .join(" ");
    }

    function getTabTitle(key, tab) {
        const raw = tab && tab.title ? String(tab.title).trim() : "";
        if (raw) return raw;
        return TAB_LABEL_FALLBACKS[key] || prettifyTabKey(key) || "Suno Songs";
    }

    function getTabDescription(key, tab) {
        const raw = tab && tab.description ? String(tab.description).trim() : "";
        if (raw) return raw;
        return TAB_DESCRIPTION_FALLBACKS[key] || "앨범 이미지를 누르면 해당 곡을 재생 또는 일시정지합니다.";
    }

    function formatInt(n) {
        try {
            return Number(n || 0).toLocaleString();
        } catch (e) {
            return "0";
        }
    }

    function formatFloat(n, digits = 2) {
        try {
            return Number(n || 0).toFixed(digits);
        } catch (e) {
            return "0.00";
        }
    }

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) return "0:00";

        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);

        return `${m}:${String(s).padStart(2, "0")}`;        
    }

function getSortableValue(song, key) {
    if (key === "rank") {
        return Number(song.rank || 0);
    }

    if (key === "rank_change") {
        if (song.rank_status === "new") return 999999;
        if (song.rank_change === null || song.rank_change === undefined || song.rank_change === "") return 0;
        return Number(song.rank_change || 0);
    }

    if (key === "has_image") {
        return song.image_url ? 1 : 0;
    }

    if (key === "title") {
        return String(song.title || "").toLowerCase();
    }

    if (key === "creator") {
        return String(song.creator || "").toLowerCase();
    }

    if (key === "style_tags") {
        return String(song.style_tags || "").toLowerCase();
    }

    if (key === "play_count") {
        return Number(song.play_count || 0);
    }

    if (key === "upvote_count") {
        return Number(song.upvote_count || 0);
    }

    if (key === "comment_count") {
        return Number(song.comment_count || 0);
    }

    return "";
}

function sortSongsForView(list) {
    if (!sortState.key || !sortState.direction) {
        return list.slice().sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
    }

    const key = sortState.key;
    const direction = sortState.direction;

    return list.slice().sort((a, b) => {
        const av = getSortableValue(a, key);
        const bv = getSortableValue(b, key);

        let result = 0;

        if (typeof av === "number" && typeof bv === "number") {
            result = av - bv;
        } else {
            result = String(av).localeCompare(String(bv), "ko", {
                numeric: true,
                sensitivity: "base",
            });
        }

        if (result === 0) {
            result = Number(a.rank || 0) - Number(b.rank || 0);
        }

        return direction === "asc" ? result : -result;
    });
}

function updateSortIndicators() {
    document.querySelectorAll("th.sortable").forEach(th => {
        const indicator = th.querySelector(".sort-indicator");
        if (!indicator) return;

        const key = th.dataset.sortKey;

        if (sortState.key !== key || !sortState.direction) {
            indicator.textContent = "";
            return;
        }

        indicator.textContent = sortState.direction === "asc" ? "▲" : "▼";
    });
}

function cycleSort(key) {
    if (sortState.key !== key) {
        sortState.key = key;
        sortState.direction = "asc";
    } else if (sortState.direction === "asc") {
        sortState.direction = "desc";
    } else if (sortState.direction === "desc") {
        sortState.key = null;
        sortState.direction = null;
    } else {
        sortState.direction = "asc";
    }

    renderTable(searchInput.value || "");
}

    function renderRankChange(value, status) {
        if (status === "new") {
            return `<span class="rank-new">NEW</span>`;
        }

        if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
            return `<span class="rank-same">-</span>`;
        }

        const n = Number(value);

        if (!isFinite(n) || n === 0) {
            return `<span class="rank-same">-</span>`;
        }

        const absN = Math.abs(Math.round(n));

        if (n > 0) {
            return `<span class="rank-up">▲${absN}</span>`;
        }

        return `<span class="rank-down">▽${absN}</span>`;
    }

    function parseStyleTags(value) {
        if (!value) return [];

        let text = String(value).trim();

        if (!text || text.toLowerCase() === "nan" || text.toLowerCase() === "none") {
            return [];
        }

        let tags = [];

        try {
            const parsed = JSON.parse(text);

            if (Array.isArray(parsed)) {
                tags = parsed.map(x => String(x).trim()).filter(Boolean);
            }
        } catch (e) {
            tags = [];
        }

        if (!tags.length) {
            tags = text
                .replaceAll("[", "")
                .replaceAll("]", "")
                .replaceAll('"', "")
                .replaceAll("'", "")
                .split(/[,|#]/)
                .map(x => x.trim())
                .filter(Boolean);
        }

        return tags;
    }

    function renderStyleTags(value) {
        const tags = parseStyleTags(value);

        if (!tags.length) {
            return `<span class="style-empty">-</span>`;
        }

        return `
            <div class="style-tags">
                ${tags.slice(0, 4).map(tag => `<span class="style-tag" title="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`).join("")}
            </div>
        `;
    }

    function renderNowStyleTags(value) {
        const tags = parseStyleTags(value);

        if (!tags.length) {
            return `<span class="now-style-empty">스타일 정보 없음</span>`;
        }

        return tags.slice(0, 8).map(tag => {
            return `<span class="now-style-tag" title="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`;
        }).join("");
    }

    function makeRequestId(prefix = "req") {
        try {
            if (window.crypto && window.crypto.randomUUID) {
                return `${prefix}-${window.crypto.randomUUID()}`;
            }
        } catch (e) {}
        return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

    function compactPlaylistSong(song) {
        if (!song) return null;
        return {
            id: String(song.id || ""),
            title: song.title || "",
            creator: song.creator || "",
            handle: song.handle || "",
            style_tags: song.style_tags || "",
            song_url: song.song_url || "",
            audio_url: song.audio_url || "",
            image_url: song.image_url || "",
            lyrics: song.lyrics || "",
            integrated_lufs: song.integrated_lufs,
            true_peak_db: song.true_peak_db,
            loudness_gain_db: song.loudness_gain_db,
        };
    }

    function currentPlaylistStatePayload() {
        const currentSong = getCurrentSong();
        return {
            playlist: playlist.map(compactPlaylistSong).filter(Boolean),
            currentSongId: currentSong ? String(currentSong.id) : null,
            currentTime: Number.isFinite(audio.currentTime) ? audio.currentTime : 0,
            duration: Number.isFinite(audio.duration) ? audio.duration : 0,
            isPlaying: false,
            audioSrc: audio && audio.src ? audio.src : null,
            repeatOne,
            repeatAll,
            playbackMode,
            volume: Number(volume.value || 80),
            loudnessNormalize,
            savedAt: Date.now(),
        };
    }

    function updateCloudPlaylistStatus(text) {
        if (cloudPlaylistStatus) {
            cloudPlaylistStatus.textContent = text || "";
        }
    }

    function cloudEnabled() {
        return Boolean(cloudConfig && cloudConfig.enabled && cloudConfig.supabaseUrl && cloudConfig.anonKey && cloudConfig.playlistToken);
    }

    function setCloudControlsEnabled(enabled) {
        [cloudSavePlaylistBtn, cloudLoadPlaylistBtn, cloudDeletePlaylistBtn, cloudPlaylistSelect].forEach(el => {
            if (el) el.disabled = !enabled;
        });
    }

    async function callCloudRpc(functionName, body) {
        if (!cloudEnabled()) {
            throw new Error((cloudConfig && cloudConfig.message) || "Cloud Playlist is not configured.");
        }
        const url = `${String(cloudConfig.supabaseUrl).replace(/[/]$/, "")}/rest/v1/rpc/${functionName}`;
        const res = await fetch(url, {
            method: "POST",
            headers: {
                "apikey": cloudConfig.anonKey,
                "Authorization": `Bearer ${cloudConfig.anonKey}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body || {}),
        });
        const text = await res.text();
        let data = null;
        if (text) {
            try { data = JSON.parse(text); } catch (e) { data = text; }
        }
        if (!res.ok) {
            const msg = data && data.message ? data.message : String(text || res.statusText || "Server RPC failed");
            throw new Error(msg);
        }
        return data;
    }

    function allKnownSongs() {
        const map = new Map();
        (Array.isArray(songs) ? songs : []).forEach(song => {
            if (song && song.id) map.set(String(song.id), song);
        });
        if (tabsData && typeof tabsData === "object") {
            Object.values(tabsData).forEach(tab => {
                (Array.isArray(tab && tab.songs) ? tab.songs : []).forEach(song => {
                    if (song && song.id && !map.has(String(song.id))) map.set(String(song.id), song);
                });
            });
        }
        return map;
    }

    async function refreshCloudPlaylistList(silent = false) {
        if (!cloudPlaylistSelect) return;
        if (!cloudEnabled()) {
            cloudPlaylistSelect.innerHTML = `<option value="">Cloud Playlist 비활성</option>`;
            updateCloudPlaylistStatus((cloudConfig && cloudConfig.message) || "로그인 후 Cloud Playlist를 사용할 수 있습니다.");
            setCloudControlsEnabled(false);
            return;
        }
        setCloudControlsEnabled(false);
        if (!silent) updateCloudPlaylistStatus("저장된 플레이리스트 불러오는 중...");
        try {
            const rows = await callCloudRpc("cloud_list_playlists", { p_token: cloudConfig.playlistToken });
            const items = Array.isArray(rows) ? rows : [];
            cloudPlaylistSelect.innerHTML = `<option value="">저장된 플레이리스트</option>` + items.map(row => {
                const count = Number(row.song_count || 0);
                const label = `${row.name || "My Playlist"} · ${count}곡`;
                return `<option value="${escapeHtml(row.id)}">${escapeHtml(label)}</option>`;
            }).join("");
            setCloudControlsEnabled(true);
            if (!silent) updateCloudPlaylistStatus(items.length ? `저장된 플레이리스트 ${items.length}개` : "아직 저장된 플레이리스트가 없습니다.");
        } catch (error) {
            console.warn("Failed to refresh cloud playlists", error);
            updateCloudPlaylistStatus(`Cloud Playlist 목록 실패: ${error.message || error}`);
            setCloudControlsEnabled(true);
        }
    }

    async function requestCloudPlaylistSave() {
        if (!playlist.length) {
            alert("저장할 플레이리스트가 비어 있습니다.");
            return;
        }
        if (!cloudEnabled()) {
            updateCloudPlaylistStatus((cloudConfig && cloudConfig.message) || "로그인 후 저장할 수 있습니다.");
            return;
        }

        const name = String(cloudPlaylistName && cloudPlaylistName.value ? cloudPlaylistName.value : "").trim()
            || `Suno Playlist ${new Date().toLocaleString()}`;
        const songIds = playlist.map(song => String(song && song.id || "").trim()).filter(Boolean);

        try {
            setCloudControlsEnabled(false);
            updateCloudPlaylistStatus(`저장 중: ${name} (${songIds.length}곡)`);
            const result = await callCloudRpc("cloud_save_playlist", {
                p_token: cloudConfig.playlistToken,
                p_name: name,
                p_song_ids: songIds,
            });
            const savedCount = result && result.song_count !== undefined ? Number(result.song_count) : songIds.length;
            updateCloudPlaylistStatus(`'${name}' 저장 완료 · ${savedCount}곡`);
            if (cloudPlaylistName) cloudPlaylistName.value = "";
            await refreshCloudPlaylistList(true);
        } catch (error) {
            console.warn("Failed to save cloud playlist", error);
            updateCloudPlaylistStatus(`저장 실패: ${error.message || error}`);
        } finally {
            setCloudControlsEnabled(true);
        }
    }

    async function loadSelectedCloudPlaylist() {
        const playlistId = cloudPlaylistSelect ? cloudPlaylistSelect.value : "";
        if (!playlistId) {
            updateCloudPlaylistStatus("불러올 플레이리스트를 선택하세요.");
            return;
        }
        try {
            setCloudControlsEnabled(false);
            updateCloudPlaylistStatus("플레이리스트 불러오는 중...");
            const rows = await callCloudRpc("cloud_get_playlist_song_ids", {
                p_token: cloudConfig.playlistToken,
                p_playlist_id: playlistId,
            });
            const songIds = (Array.isArray(rows) ? rows : []).map(row => String(row.song_id || "")).filter(Boolean);
            const songMap = allKnownSongs();
            const loaded = songIds.map(id => songMap.get(String(id))).filter(song => song && song.audio_url);
            if (!loaded.length) {
                updateCloudPlaylistStatus("현재 payload에서 재생 가능한 곡을 찾지 못했습니다. archive lookup 연결 후 복원 가능합니다.");
                return;
            }
            const state = {
                playlist: loaded,
                currentSongId: String(loaded[0].id),
                currentTime: 0,
                duration: 0,
                isPlaying: false,
                audioSrc: loaded[0].audio_url || null,
                repeatOne: false,
                repeatAll: true,
                playbackMode: "sequence",
                volume: Number(volume.value || 80),
                loudnessNormalize,
                savedAt: Date.now(),
            };
            applyPlaylistState(state, { allowAutoplay: false, persist: true });
            updateCloudPlaylistStatus(`불러오기 완료 · ${loaded.length}곡`);
        } catch (error) {
            console.warn("Failed to load cloud playlist", error);
            updateCloudPlaylistStatus(`불러오기 실패: ${error.message || error}`);
        } finally {
            setCloudControlsEnabled(true);
        }
    }

    async function deleteSelectedCloudPlaylist() {
        const playlistId = cloudPlaylistSelect ? cloudPlaylistSelect.value : "";
        if (!playlistId) {
            updateCloudPlaylistStatus("삭제할 플레이리스트를 선택하세요.");
            return;
        }
        if (!confirm("선택한 Cloud Playlist를 삭제할까요?")) return;
        try {
            setCloudControlsEnabled(false);
            await callCloudRpc("cloud_delete_playlist", {
                p_token: cloudConfig.playlistToken,
                p_playlist_id: playlistId,
            });
            updateCloudPlaylistStatus("삭제 완료");
            await refreshCloudPlaylistList(true);
        } catch (error) {
            console.warn("Failed to delete cloud playlist", error);
            updateCloudPlaylistStatus(`삭제 실패: ${error.message || error}`);
        } finally {
            setCloudControlsEnabled(true);
        }
    }

    function savePlaylistState(force = false) {
        if (!playerEnabled) return;
        if (suppressStateSave && !force) return;

        try {
            const currentSong = getCurrentSong();
            const hasActiveAudio = Boolean(currentSong && audio && audio.src);
            const currentTime = hasActiveAudio && Number.isFinite(audio.currentTime)
                ? audio.currentTime
                : 0;
            const duration = hasActiveAudio && Number.isFinite(audio.duration)
                ? audio.duration
                : 0;
            const isPlaying = hasActiveAudio && !audio.paused && !audio.ended;
            const state = {
                playlist,
                currentSongId: currentSong ? String(currentSong.id) : null,
                currentTime,
                duration,
                isPlaying,
                audioSrc: hasActiveAudio ? audio.src : null,
                repeatOne,
                repeatAll,
                playbackMode,
                volume: Number(volume.value || 75),
                loudnessNormalize,
                savedAt: Date.now(),
            };
            window.localStorage.setItem(playlistStorageKey, JSON.stringify(state));
        } catch (error) {
            console.warn("Failed to save playlist state", error);
        }
    }

    function savePlaylistStateThrottled() {
        const now = Date.now();
        if (now - lastStateSaveAt < 1000) return;
        lastStateSaveAt = now;
        savePlaylistState();
    }

    function applyPlaylistState(state, options = {}) {
        const restored = Array.isArray(state && state.playlist) ? state.playlist : [];

        playlist = restored.filter(song => song && song.id && song.audio_url);
        currentIndex = -1;

        if (state && state.currentSongId) {
            currentIndex = playlist.findIndex(song => String(song.id) === String(state.currentSongId));
        }

        if (currentIndex < 0 && playlist.length > 0) {
            currentIndex = 0;
        }

        repeatOne = Boolean(state && state.repeatOne);
        repeatAll = !state || state.repeatAll === undefined ? repeatAll : Boolean(state.repeatAll);
        playbackMode = state && state.playbackMode === "shuffle" ? "shuffle" : "sequence";
        loudnessNormalize = Boolean(state && state.loudnessNormalize);

        if (state && state.volume !== undefined && volume) {
            volume.value = Math.min(100, Math.max(0, Number(state.volume) || 75));
        }

        if (currentIndex >= 0) {
            loadCurrent(false, {
                restoreTime: Number((state && state.currentTime) || 0),
                restoreAutoplay: Boolean(state && state.isPlaying && options.allowAutoplay),
                skipInitialSave: true,
            });
        } else {
            audio.pause();
            audio.removeAttribute("src");
            progress.value = 0;
            currentTimeEl.textContent = "0:00";
            durationEl.textContent = "0:00";
            updateNowPlaying(null);
            playBtn.textContent = "▶";
        }

        renderPlaylist();
        refreshButtonsAndCovers();
        refreshModeButtons();
        updateVolume();

        if (options.persist) {
            savePlaylistState(true);
        }
    }

    function restorePlaylistState() {
        try {
            const raw = window.localStorage.getItem(playlistStorageKey);
            if (!raw) return;
            applyPlaylistState(JSON.parse(raw), { allowAutoplay: true, persist: false });
        } catch (error) {
            console.warn("Failed to restore playlist state", error);
            playlist = [];
            currentIndex = -1;
        }
    }

    function applyCloudPlaylistLoadRequest(force = false) {
        try {
            const raw = window.localStorage.getItem(cloudLoadRequestStorageKey);
            if (!raw) return;

            const request = JSON.parse(raw);
            const requestId = String(request.loadRequestId || request.at || "");
            if (!requestId) return;
            if (!force && requestId === lastCloudLoadRequestId) return;

            lastCloudLoadRequestId = requestId;
            const state = request.state || request.loadState || request;
            applyPlaylistState(state, { allowAutoplay: false, persist: true });

            if (typeof updateCloudPlaylistStatus === "function") {
                const count = Array.isArray(state.playlist) ? state.playlist.length : 0;
                updateCloudPlaylistStatus(`클라우드 플레이리스트 불러오기 완료 (${count}곡)`);
            }
        } catch (error) {
            console.warn("Failed to apply cloud playlist load request", error);
        }
    }

    function getCurrentSong() {
        if (currentIndex < 0 || currentIndex >= playlist.length) return null;
        return playlist[currentIndex];
    }

    function getSongById(id) {
        return songs.find(s => String(s.id) === String(id));
    }

    function isCurrentSong(song) {
        const current = getCurrentSong();
        return current && String(current.id) === String(song.id);
    }

    function dbToGain(db) {
        const n = Number(db);
        if (!Number.isFinite(n)) return 1;
        return Math.pow(10, n / 20);
    }

    function currentLoudnessGainDb() {
        const song = getCurrentSong();
        if (!song || !loudnessNormalize) return 0;
        const gain = Number(song.loudness_gain_db);
        if (!Number.isFinite(gain)) return 0;
        return Math.min(6, Math.max(-12, gain));
    }

    function currentLoudnessLabel() {
        const song = getCurrentSong();
        if (!loudnessNormalize) return "LUFS 정규화 꺼짐";
        if (!song) return "-14 LUFS 정규화 켜짐";

        const gain = Number(song.loudness_gain_db);
        const lufs = Number(song.integrated_lufs);
        const tp = Number(song.true_peak_db);

        if (!Number.isFinite(gain)) {
            return "LUFS 미분석 곡: 기본 볼륨";
        }

        const sign = gain > 0 ? "+" : "";
        const parts = [`gain ${sign}${gain.toFixed(1)} dB`];
        if (Number.isFinite(lufs)) parts.push(`${lufs.toFixed(1)} LUFS`);
        if (Number.isFinite(tp)) parts.push(`${tp.toFixed(1)} dBTP`);
        if (gain > 0) parts.push("boost는 브라우저 볼륨 한도 내 적용");
        return parts.join(" · ");
    }

    function ensureAudioGraph() {
        if (webAudioReady || webAudioFailed) return webAudioReady;

        try {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) {
                webAudioFailed = true;
                return false;
            }

            audioContext = audioContext || new Ctx();
            audioSourceNode = audioSourceNode || audioContext.createMediaElementSource(audio);
            loudnessGainNode = loudnessGainNode || audioContext.createGain();
            audioSourceNode.connect(loudnessGainNode);
            loudnessGainNode.connect(audioContext.destination);
            webAudioReady = true;
            return true;
        } catch (error) {
            console.warn("Web Audio normalization unavailable; falling back to element volume", error);
            webAudioFailed = true;
            return false;
        }
    }

    function resumeAudioContext() {
        try {
            if (audioContext && audioContext.state === "suspended") {
                audioContext.resume();
            }
        } catch (error) {
            console.warn("AudioContext resume failed", error);
        }
    }

    function updateLoudnessUi() {
        if (loudnessNormalizeBtn) {
            loudnessNormalizeBtn.classList.toggle("active", loudnessNormalize);
            loudnessNormalizeBtn.textContent = loudnessNormalize ? "-14 LUFS ON" : "-14 LUFS OFF";
        }
        if (loudnessStatus) {
            loudnessStatus.textContent = currentLoudnessLabel();
        }
    }

    function updateVolume() {
        const userVolume = Number(volume.value || 80) / 100;
        const gainDb = currentLoudnessGainDb();
        const gainMul = loudnessNormalize ? dbToGain(gainDb) : 1;

        volumeText.textContent = `${Math.round(userVolume * 100)}%`;

        // IMPORTANT:
        // Suno audio URLs can be cross-origin. Connecting a cross-origin
        // HTMLAudioElement to Web Audio may produce silence in browsers unless
        // the media response has the right CORS headers. To avoid muting playback,
        // keep the main player on the native <audio> output path and apply the
        // safe part of loudness normalization through element.volume.
        // This fully supports cutting loud tracks. Positive boosts are applied
        // only up to the browser volume ceiling of 1.0.
        audio.volume = Math.min(1, Math.max(0, userVolume * gainMul));

        updateLoudnessUi();
    }

    function renderTable(filterText = "") {
        const q = String(filterText || "").trim().toLowerCase();

        let filtered = songs.filter(song => {
            if (!q) return true;

            const hay = [
                song.title,
                song.style_tags,
                song.creator,
                song.handle,
                song.id
            ].join(" ").toLowerCase();

            return hay.includes(q);
        });

        filtered = sortSongsForView(filtered);

        if (!q) {
            filtered = filtered.slice(0, 200);
        }

        updateSortIndicators();

        if (!filtered.length) {
            songTableBody.innerHTML = `
                <tr>
                    <td colspan="11" style="padding:18px; text-align:center; color:#6b7280;">
                        표시할 곡이 없습니다.
                    </td>
                </tr>
            `;
            return;
        }

        songTableBody.innerHTML = filtered.map(song => {
            const imageHtml = song.image_url
                ? `<img class="cover" src="${escapeHtml(song.image_url)}" loading="lazy">`
                : `<div class="cover"></div>`;

            const titleHtml = song.song_url
                ? `<a class="title-link" href="${escapeHtml(song.song_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(song.title)}</a>`
                : `<span class="title-link">${escapeHtml(song.title)}</span>`;

            const handleHtml = song.handle
                ? `<div class="subtle">${escapeHtml(song.handle)}</div>`
                : "";

            const creatorUrl = creatorProfileUrl(song);
            const creatorHtml = creatorUrl
                ? `<a class="creator-link" href="${escapeHtml(creatorUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(song.creator)}</a>`
                : escapeHtml(song.creator);

            const outlierClass = song.is_outlier ? "outlier-row" : "";
            const outlierBadge = song.is_outlier
                ? `<span class="outlier-badge" title="${escapeHtml(song.outlier_reasons)}">⚠</span>`
                : "";

            return `
                <tr class="${outlierClass}" data-song-id="${escapeHtml(song.id)}">
                    <td class="select-cell">
                        <button class="add-btn" data-action="toggle-playlist" data-song-id="${escapeHtml(song.id)}" title="선택 / 해제">+</button>
                    </td>
                    <td class="rank">${song.rank}</td>
                    <td class="rank-change">${renderRankChange(song.rank_change, song.rank_status)}</td>
                    <td>
                        <div class="cover-cell">
                            <button class="cover-btn" data-action="cover-click" data-song-id="${escapeHtml(song.id)}" title="재생 / 일시정지">
                                ${imageHtml}
                            </button>
                        </div>
                    </td>
                    <td class="title-cell">
                        ${titleHtml} ${outlierBadge}
                        <div class="subtle">${escapeHtml(song.created_at)}</div>
                    </td>
                    <td class="style-cell">
                        ${renderStyleTags(song.style_tags)}
                    </td>
                    <td class="creator">
                        ${creatorHtml}
                        ${handleHtml}
                    </td>
                    <td class="num">${formatInt(song.play_count)}</td>
                    <td class="num">${formatInt(song.upvote_count)}</td>
                    <td class="num">${formatInt(song.comment_count)}</td>
                    <td style="text-align:center;">
                        <button class="rank-info-btn" data-action="rank-info" data-song-id="${escapeHtml(song.id)}">상세정보</button>
                    </td>
                </tr>
            `;
        }).join("");

        bindTableEvents();
        refreshButtonsAndCovers();
    }

    function bindTableEvents() {
        songTableBody.querySelectorAll("[data-action='toggle-playlist']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                togglePlaylist(btn.dataset.songId);
            });
        });

        songTableBody.querySelectorAll("[data-action='cover-click']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                coverClick(btn.dataset.songId);
            });
        });

        songTableBody.querySelectorAll("[data-action='rank-info']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                openRankingInfo(btn.dataset.songId);
            });
        });
    }

    function bindSortHeaderEvents() {
        document.querySelectorAll("th.sortable").forEach(th => {
            th.addEventListener("click", event => {
                event.preventDefault();

                const key = th.dataset.sortKey;
                if (!key) return;

                cycleSort(key);
            });
        });
    }

    function bindPlaylistEvents() {
        playlistEl.querySelectorAll("[data-action='play-playlist-index']").forEach(item => {
            item.addEventListener("click", event => {
                event.preventDefault();
                playPlaylistIndex(Number(item.dataset.index));
            });
        });

        playlistEl.querySelectorAll("[data-action='remove-playlist']").forEach(btn => {
            btn.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                removeFromPlaylistById(btn.dataset.songId);
            });
        });
    }

    function addToPlaylist(id) {
        const song = getSongById(id);

        if (!song) return false;

        if (!song.audio_url) {
            alert("이 곡에는 audio_url이 없습니다.");
            return false;
        }

        if (!playlist.some(s => String(s.id) === String(song.id))) {
            playlist.push(song);
        }

        if (currentIndex === -1) {
            currentIndex = playlist.findIndex(s => String(s.id) === String(song.id));
            loadCurrent(false);
        }

        renderPlaylist();
        refreshButtonsAndCovers();
        savePlaylistState();

        return true;
    }

    function removeFromPlaylistById(id) {
        const idx = playlist.findIndex(s => String(s.id) === String(id));

        if (idx < 0) return;

        const wasCurrent = idx === currentIndex;

        playlist.splice(idx, 1);

        if (playlist.length === 0) {
            currentIndex = -1;
            audio.pause();
            audio.removeAttribute("src");
            updateNowPlaying(null);
        } else {
            if (idx < currentIndex) {
                currentIndex -= 1;
            } else if (wasCurrent) {
                currentIndex = Math.min(idx, playlist.length - 1);
                loadCurrent(false);
            }
        }

        renderPlaylist();
        refreshButtonsAndCovers();
        savePlaylistState();
    }

    function togglePlaylist(id) {
        if (!playerEnabled) {
            coverClick(id);
            return;
        }

        const exists = playlist.some(s => String(s.id) === String(id));

        if (exists) {
            removeFromPlaylistById(id);
        } else {
            addToPlaylist(id);
        }
    }

    function coverClick(id) {
        const song = getSongById(id);

        if (!song) return;

        if (!playerEnabled) {
            publicCoverClick(song);
            return;
        }

        if (!playlist.some(s => String(s.id) === String(id))) {
            const added = addToPlaylist(id);
            if (!added) return;
        }

        const idx = playlist.findIndex(s => String(s.id) === String(id));

        if (idx < 0) return;

        if (currentIndex === idx) {
            togglePlay();
        } else {
            currentIndex = idx;
            loadCurrent(true);
            savePlaylistState();
        }
    }

    function publicCoverClick(song) {
        if (!song || !song.audio_url) {
            alert("이 곡에는 audio_url이 없습니다.");
            return;
        }

        const sameSong = currentSong && String(currentSong.id) === String(song.id);
        if (sameSong) {
            togglePlay();
            return;
        }

        playlist = [song];
        currentIndex = 0;
        loadCurrent(true, { skipInitialSave: true });
    }

    function renderPlaylist() {
        playlistCount.textContent = `${playlist.length} tracks`;

        if (playlist.length === 0) {
            playlistEl.innerHTML = `
                <div class="playlist-empty">
                    아직 플레이리스트가 비어 있습니다.<br>
                    오른쪽 랭킹에서 앨범 이미지나 체크 버튼을 눌러 추가하세요.
                </div>
            `;
            return;
        }

        playlistEl.innerHTML = playlist.map((song, idx) => {
            const active = idx === currentIndex ? "active" : "";
            const thumb = song.image_url
                ? `<img class="playlist-thumb" src="${escapeHtml(song.image_url)}" loading="lazy">`
                : `<div class="playlist-thumb"></div>`;

            return `
                <div class="playlist-item ${active}" data-action="play-playlist-index" data-index="${idx}">
                    ${thumb}
                    <div class="playlist-meta">
                        <div class="playlist-song-title">${escapeHtml(song.title)}</div>
                        <div class="playlist-song-sub">${escapeHtml(song.creator)} ${escapeHtml(song.handle || "")}</div>
                    </div>
                    <button class="remove-btn" data-action="remove-playlist" data-song-id="${escapeHtml(song.id)}">×</button>
                </div>
            `;
        }).join("");

        bindPlaylistEvents();
    }

    function refreshButtonsAndCovers() {
        document.querySelectorAll(".add-btn[data-song-id]").forEach(btn => {
            const id = btn.dataset.songId;
            const added = playlist.some(s => String(s.id) === String(id));

            if (added) {
                btn.classList.add("added");
                btn.textContent = "✓";
            } else {
                btn.classList.remove("added");
                btn.textContent = "+";
            }
        });

        document.querySelectorAll(".cover-btn[data-song-id]").forEach(cover => {
            const id = cover.dataset.songId;
            const song = getSongById(id);

            cover.classList.remove("playing");
            cover.classList.remove("paused");

            if (song && isCurrentSong(song)) {
                if (audio.paused) {
                    cover.classList.add("paused");
                } else {
                    cover.classList.add("playing");
                }
            }
        });
    }

    function playPlaylistIndex(idx) {
        if (idx < 0 || idx >= playlist.length) return;

        if (currentIndex === idx) {
            togglePlay();
        } else {
            currentIndex = idx;
            loadCurrent(true);
            savePlaylistState();
        }
    }

    function updateNowPlaying(song) {
        if (!song) {
            nowCoverWrap.innerHTML = `<div class="now-placeholder">No track selected</div>`;
            nowTitle.textContent = "플레이리스트에 곡을 추가하세요";
            nowCreator.textContent = "앨범 이미지나 체크 버튼을 누르면 추가됩니다.";
            nowStyleTags.innerHTML = "";
            lyricsPanel.textContent = "가사/프롬프트 정보가 있으면 여기에 표시됩니다.";
            lyricsPanel.classList.add("empty");
            playBtn.textContent = "▶";
            progress.value = 0;
            currentTimeEl.textContent = "0:00";
            durationEl.textContent = "0:00";
            refreshButtonsAndCovers();
            return;
        }

        if (song.image_url) {
            nowCoverWrap.innerHTML = `<img class="now-cover" src="${escapeHtml(song.image_url)}">`;
        } else {
            nowCoverWrap.innerHTML = `<div class="now-placeholder">No image</div>`;
        }

        nowTitle.textContent = song.title;
        nowCreator.textContent = `${song.creator || ""} ${song.handle || ""}`.trim();
        nowStyleTags.innerHTML = renderNowStyleTags(song.style_tags);

        if (song.lyrics && song.lyrics.trim()) {
            lyricsPanel.textContent = song.lyrics;
            lyricsPanel.classList.remove("empty");
        } else {
            lyricsPanel.textContent = "가사/프롬프트 정보가 아직 수집되지 않았습니다.";
            lyricsPanel.classList.add("empty");
        }

        updateVolume();
        refreshButtonsAndCovers();
    }

    function loadCurrent(autoplay, options = {}) {
        if (currentIndex < 0 || currentIndex >= playlist.length) {
            updateNowPlaying(null);
            return;
        }

        const song = playlist[currentIndex];

        updateNowPlaying(song);
        renderPlaylist();

        if (!song.audio_url) {
            alert("이 곡에는 audio_url이 없습니다.");
            return;
        }

        const restoreTime = Number(options.restoreTime || 0);
        const shouldAutoplay = Boolean(autoplay || options.restoreAutoplay);
        const isRestoreAutoplay = Boolean(options.restoreAutoplay && !autoplay);

        suppressStateSave = true;
        audio.pause();
        // Keep native audio output. Do not force crossOrigin here; some Suno
        // media URLs may stop playing when anonymous CORS is requested.
        audio.removeAttribute("crossorigin");
        audio.src = song.audio_url;
        audio.load();
        updateVolume();
        suppressStateSave = false;

        const startPlayback = () => {
            updateVolume();
            audio.play()
                .then(() => {
                    playBtn.textContent = "Ⅱ";
                    refreshButtonsAndCovers();
                    savePlaylistState(true);
                })
                .catch(err => {
                    console.log(err);
                    playBtn.textContent = "▶";
                    refreshButtonsAndCovers();
                    savePlaylistState(true);
                    if (!isRestoreAutoplay) {
                        alert("브라우저가 오디오 재생을 막았거나 URL을 재생할 수 없습니다.");
                    }
                });
        };

        const restorePositionAndMaybePlay = () => {
            if (restoreTime > 0 && Number.isFinite(audio.duration) && audio.duration > 0) {
                audio.currentTime = Math.min(Math.max(0, restoreTime), Math.max(0, audio.duration - 0.25));
            }

            if (shouldAutoplay) {
                startPlayback();
            } else {
                playBtn.textContent = "▶";
                refreshButtonsAndCovers();
                if (!options.skipInitialSave) savePlaylistState(true);
            }
        };

        if (restoreTime > 0 || shouldAutoplay) {
            audio.addEventListener("loadedmetadata", restorePositionAndMaybePlay, { once: true });
        } else {
            playBtn.textContent = "▶";
            refreshButtonsAndCovers();
            if (!options.skipInitialSave) savePlaylistState(true);
        }
    }

    function togglePlay() {
        if (currentIndex === -1) {
            if (playlist.length > 0) {
                currentIndex = 0;
                loadCurrent(true);
            }

            return;
        }

        if (audio.paused) {
            updateVolume();
            audio.play()
                .then(() => {
                    playBtn.textContent = "Ⅱ";
                    refreshButtonsAndCovers();
                })
                .catch(err => {
                    console.log(err);
                    alert("브라우저가 오디오 재생을 막았거나 URL을 재생할 수 없습니다.");
                });
        } else {
            audio.pause();
            playBtn.textContent = "▶";
            refreshButtonsAndCovers();
        }
    }

    function getRandomNextIndex() {
        if (playlist.length <= 1) return currentIndex;

        let next = currentIndex;

        while (next === currentIndex) {
            next = Math.floor(Math.random() * playlist.length);
        }

        return next;
    }

    function playNext() {
        if (playlist.length === 0) return;

        if (playbackMode === "shuffle") {
            currentIndex = getRandomNextIndex();
            loadCurrent(true);
            return;
        }

        if (currentIndex < playlist.length - 1) {
            currentIndex += 1;
            loadCurrent(true);
        } else if (repeatAll) {
            currentIndex = 0;
            loadCurrent(true);
        } else {
            audio.pause();
            playBtn.textContent = "▶";
            refreshButtonsAndCovers();
        }
    }

    function playPrev() {
        if (playlist.length === 0) return;

        if (audio.currentTime > 3) {
            audio.currentTime = 0;
            return;
        }

        if (playbackMode === "shuffle") {
            currentIndex = getRandomNextIndex();
            loadCurrent(true);
            return;
        }

        if (currentIndex > 0) {
            currentIndex -= 1;
            loadCurrent(true);
        } else if (repeatAll) {
            currentIndex = playlist.length - 1;
            loadCurrent(true);
        }
    }

    function refreshModeButtons() {
        repeatOneBtn.classList.toggle("active", repeatOne);
        repeatAllBtn.classList.toggle("active", repeatAll);
        sequenceBtn.classList.toggle("active", playbackMode === "sequence");
        shuffleBtn.classList.toggle("active", playbackMode === "shuffle");
    }

    if (cloudSavePlaylistBtn) {
        cloudSavePlaylistBtn.addEventListener("click", requestCloudPlaylistSave);
    }
    if (cloudLoadPlaylistBtn) {
        cloudLoadPlaylistBtn.addEventListener("click", loadSelectedCloudPlaylist);
    }
    if (cloudDeletePlaylistBtn) {
        cloudDeletePlaylistBtn.addEventListener("click", deleteSelectedCloudPlaylist);
    }

    playBtn.addEventListener("click", togglePlay);
    nextBtn.addEventListener("click", playNext);
    prevBtn.addEventListener("click", playPrev);

    repeatOneBtn.addEventListener("click", () => {
        repeatOne = !repeatOne;

        if (repeatOne) {
            repeatAll = false;
        }

        refreshModeButtons();
        savePlaylistState();
    });

    repeatAllBtn.addEventListener("click", () => {
        repeatAll = !repeatAll;

        if (repeatAll) {
            repeatOne = false;
        }

        refreshModeButtons();
        savePlaylistState();
    });

    sequenceBtn.addEventListener("click", () => {
        playbackMode = "sequence";
        refreshModeButtons();
        savePlaylistState();
    });

    shuffleBtn.addEventListener("click", () => {
        playbackMode = "shuffle";
        refreshModeButtons();
        savePlaylistState();
    });

    clearBtn.addEventListener("click", () => {
        playlist = [];
        currentIndex = -1;
        audio.pause();
        audio.removeAttribute("src");
        updateNowPlaying(null);
        renderPlaylist();
        refreshButtonsAndCovers();
        savePlaylistState();
    });

    volume.addEventListener("input", () => {
        updateVolume();
        savePlaylistState();
    });

    if (loudnessNormalizeBtn) {
        loudnessNormalizeBtn.addEventListener("click", () => {
            loudnessNormalize = !loudnessNormalize;
            updateVolume();
            savePlaylistState(true);
        });
    }

    progress.addEventListener("input", () => {
        if (!isFinite(audio.duration) || audio.duration <= 0) return;

        audio.currentTime = (Number(progress.value) / 1000) * audio.duration;
        savePlaylistState(true);
    });

    audio.addEventListener("timeupdate", () => {
        if (isFinite(audio.duration) && audio.duration > 0) {
            progress.value = Math.round((audio.currentTime / audio.duration) * 1000);
            currentTimeEl.textContent = formatTime(audio.currentTime);
            durationEl.textContent = formatTime(audio.duration);
            savePlaylistStateThrottled();
        }
    });

    audio.addEventListener("loadedmetadata", () => {
        durationEl.textContent = formatTime(audio.duration);
        updateVolume();
    });

    audio.addEventListener("play", () => {
        playBtn.textContent = "Ⅱ";
        refreshButtonsAndCovers();
        savePlaylistState(true);
    });

    audio.addEventListener("pause", () => {
        playBtn.textContent = "▶";
        refreshButtonsAndCovers();
        savePlaylistState(true);
    });

    audio.addEventListener("ended", () => {
        if (repeatOne) {
            audio.currentTime = 0;
            audio.play();
        } else {
            playNext();
        }
    });

    searchInput.addEventListener("input", () => {
        renderTable(searchInput.value);
    });

    function openRankingInfo(id) {
        const song = getSongById(id);

        if (!song) return;

        modalTitle.textContent = `#${song.rank} ${song.title}`;
        modalSub.textContent = `${song.creator || ""} ${song.handle || ""}`.trim();

        scoreTrend.textContent = formatFloat(song.trend_score);
        scoreBase.textContent = formatFloat(song.base_score);
        scoreGrowth.textContent = formatFloat(song.growth_score);
        scoreFreshness.textContent = formatFloat(song.freshness_score);

        rankingModal.classList.add("open");
        drawHistoryChart(id);
    }

    function drawHistoryChart(id) {
        const ctx = historyCanvas.getContext("2d");
        const w = historyCanvas.width;
        const h = historyCanvas.height;

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, w, h);

        const rows = histories[String(id)] || [];

        ctx.fillStyle = "#6b7280";
        ctx.font = "12px Arial";

        if (!rows.length) {
            ctx.fillText("히스토리 데이터가 아직 없습니다.", 20, 40);
            return;
        }

        const padL = 54;
        const padR = 18;
        const padT = 18;
        const padB = 36;
        const chartW = w - padL - padR;
        const chartH = h - padT - padB;

        const maxVal = Math.max(
            1,
            ...rows.map(r => Math.max(r.play_count || 0, r.upvote_count || 0, r.comment_count || 0))
        );

        function xAt(i) {
            if (rows.length <= 1) return padL;
            return padL + (i / (rows.length - 1)) * chartW;
        }

        function yAt(v) {
            return padT + chartH - ((v || 0) / maxVal) * chartH;
        }

        ctx.strokeStyle = "#e5e7eb";
        ctx.lineWidth = 1;

        for (let i = 0; i <= 4; i++) {
            const y = padT + (chartH / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(w - padR, y);
            ctx.stroke();

            const label = Math.round(maxVal - (maxVal / 4) * i);
            ctx.fillStyle = "#6b7280";
            ctx.fillText(formatInt(label), 6, y + 4);
        }

        function drawLine(key, color, label, labelX) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();

            rows.forEach((r, i) => {
                const x = xAt(i);
                const y = yAt(r[key]);

                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });

            ctx.stroke();

            ctx.fillStyle = color;
            ctx.fillText(label, labelX, 14);
        }

        drawLine("play_count", "#111827", "play", padL);
        drawLine("upvote_count", "#ef4444", "like", padL + 52);
        drawLine("comment_count", "#2563eb", "comment", padL + 100);

        ctx.fillStyle = "#6b7280";
        ctx.fillText(rows[0].checked_at || "", padL, h - 12);
        ctx.fillText(rows[rows.length - 1].checked_at || "", w - padR - 80, h - 12);
    }

    modalCloseBtn.addEventListener("click", () => {
        rankingModal.classList.remove("open");
    });

    rankingModal.addEventListener("click", event => {
        if (event.target === rankingModal) {
            rankingModal.classList.remove("open");
        }
    });

    function resetPlayerForTabSwitch() {
        playlist = [];
        currentIndex = -1;
        audio.pause();
        audio.removeAttribute("src");
        progress.value = 0;
        currentTimeEl.textContent = "0:00";
        durationEl.textContent = "0:00";
        updateNowPlaying(null);
        renderPlaylist();
        refreshButtonsAndCovers();
    }

    function setActiveTabButton(activeKey) {
        if (!rankViewTabs) return;
        rankViewTabs.querySelectorAll(".rank-view-tab").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.tabKey === activeKey);
        });
    }

    function activateRankTab(key, resetPlayer = true) {
        if (!tabsData || !tabsData[key]) return;

        const tab = tabsData[key] || {};
        songs = Array.isArray(tab.songs) ? tab.songs : [];
        histories = tab.histories || {};

        if (rankingTitle) rankingTitle.textContent = getTabTitle(key, tab);
        if (rankingSub) rankingSub.textContent = getTabDescription(key, tab);

        sortState = { key: null, direction: null };
        setActiveTabButton(key);

        if (searchInput) searchInput.value = "";
        if (resetPlayer) resetPlayerForTabSwitch();
        renderTable("");
    }

    function initRankTabs() {
        const hasTabs = tabsData && typeof tabsData === "object" && Array.isArray(tabsOrder) && tabsOrder.length > 0;

        if (!hasTabs || !rankViewTabs) {
            if (rankViewTabs) rankViewTabs.style.display = "none";
            return false;
        }

        rankViewTabs.innerHTML = "";

        tabsOrder.forEach(key => {
            const tab = tabsData[key];
            if (!tab) return;

            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "rank-view-tab";
            btn.dataset.tabKey = key;
            btn.textContent = getTabTitle(key, tab);
            btn.addEventListener("click", () => activateRankTab(key, false));
            rankViewTabs.appendChild(btn);
        });

        const initialKey = tabsData[defaultTabKey] ? defaultTabKey : tabsOrder.find(key => tabsData[key]);

        if (initialKey) {
            activateRankTab(initialKey, false);
            return true;
        }

        return false;
    }

    window.addEventListener("pagehide", () => savePlaylistState(true));
    window.addEventListener("beforeunload", () => savePlaylistState(true));

    bindSortHeaderEvents();
    const tabsInitialized = initRankTabs();
    if (!tabsInitialized) {
        renderTable("");
    }
    if (playerEnabled) {
        restorePlaylistState();
        refreshCloudPlaylistList(true);
    }
    renderPlaylist();
    refreshModeButtons();
    updateVolume();
    </script>
    """

    def _b64_json_payload(value):
        if value is None:
            value = "null"
        return base64.b64encode(str(value).encode("utf-8")).decode("ascii")

    full_html = (
        html_template
        .replace("{title_html}", title_html)
        .replace("{subtitle_html}", subtitle_html)
        .replace("{shell_extra_class}", shell_extra_class)
        .replace("__SONGS_JSON_B64__", _b64_json_payload(songs_json))
        .replace("__HISTORIES_JSON_B64__", _b64_json_payload(histories_json))
        .replace("__RANKING_CONFIG_JSON_B64__", _b64_json_payload(ranking_config_json))
        .replace("__TABS_JSON_B64__", _b64_json_payload(tabs_json or "null"))
        .replace("__TABS_ORDER_JSON_B64__", _b64_json_payload(tabs_order_json or "[]"))
        .replace("__DEFAULT_TAB_KEY__", default_tab_key_js)
        .replace("__CLOUD_CONFIG_JSON_B64__", _b64_json_payload(cloud_config_json or "{}"))
    )

    components.html(
        full_html,
        height=1220,
        scrolling=False,
    )


