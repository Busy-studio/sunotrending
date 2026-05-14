"""Busy Chart two-panel HTML/JavaScript player and chart component."""

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
    title="Busy Chart",
    subtitle=None,
    tabs_json="null",
    tabs_order_json="[]",
    default_tab_key="",
    cloud_config_json="{}",
):
    title = clean_payload_text(title) or "Busy Chart"
    subtitle = clean_payload_text(subtitle) or "앨범 이미지를 누르면 재생/일시정지됩니다."
    title_html = html.escape(title)
    subtitle_html = html.escape(subtitle)
    default_tab_key_js = json.dumps(default_tab_key or "", ensure_ascii=False)

    html_template = """
    <style>
    :root {
      --bg:#fbf8f1; --panel:#fffdf8; --panel2:#f7f1e7; --line:#e7ddd0; --line2:#d3c6b6;
      --text:#24211e; --muted:#7b7167; --accent:#6f7f63; --accent-dark:#2f3a2f; --soft:#f1eadf;
    }
    *{box-sizing:border-box}
    html, body { margin:0; padding:0; background:transparent; color:var(--text); font-family:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic","Segoe UI",Arial,sans-serif; }
    button,input,select{font-family:inherit}
    .app-shell{width:100%; height:1030px; display:grid; grid-template-columns:minmax(720px, 1fr) minmax(300px, 370px); gap:12px; align-items:stretch; overflow:hidden;}
    .ranking-panel,.player-panel{min-width:0; height:100%; background:rgba(255,253,248,.90); border:1px solid var(--line); border-radius:18px; box-shadow:0 14px 42px rgba(72,60,47,.06); overflow:hidden;}
    .ranking-panel{display:flex; flex-direction:column;}
    .player-panel{display:flex; flex-direction:column; padding:12px;}
    .ranking-topbar{display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:12px; background:rgba(255,253,248,.94); border-bottom:1px solid var(--line);}
    .rank-view-tabs{display:flex; flex-wrap:wrap; gap:7px; margin-bottom:8px;}
    .rank-view-tab{border:1px solid var(--line2); background:#fff; color:var(--muted); border-radius:999px; padding:6px 11px; font-size:12px; font-weight:900; cursor:pointer;}
    .rank-view-tab.active{background:var(--accent); color:#fff; border-color:var(--accent);}
    .ranking-title{font-size:17px; font-weight:1000; letter-spacing:-.02em;}
    .ranking-sub{font-size:12px; color:var(--muted); margin-top:3px;}
    .search-input{border:1px solid var(--line2); border-radius:999px; padding:9px 13px; min-width:250px; max-width:340px; outline:none; background:#fff; color:var(--text);}
    .search-input:focus{border-color:var(--accent)}
    .table-wrap{flex:1; min-height:0; overflow:auto; width:100%; background:#fffdf8;}
    table.song-table{width:100%; min-width:790px; border-collapse:collapse; table-layout:fixed; font-size:13px; color:var(--text);}
    .song-table th{position:sticky; top:0; z-index:2; text-align:left; padding:9px 6px; background:var(--soft); border-bottom:1px solid var(--line2); font-weight:900; white-space:nowrap;}
    .song-table th.sortable{cursor:pointer; user-select:none;}
    .song-table td{padding:7px 6px; border-bottom:1px solid var(--line); vertical-align:middle;}
    .song-table tr:hover{background:#faf7f0;}
    .rank{font-size:16px; font-weight:1000; text-align:right; font-variant-numeric:tabular-nums;}
    .cover-btn{width:48px; height:48px; border:0; padding:0; margin:0; background:transparent; cursor:pointer; position:relative; display:block;}
    .cover{width:48px; height:48px; border-radius:11px; object-fit:cover; background:#e5e0d8; display:block;}
    .cover-btn::after{content:"▶"; position:absolute; right:4px; bottom:4px; width:20px; height:20px; border-radius:999px; background:rgba(47,58,47,.86); color:#fff; font-size:11px; line-height:20px; text-align:center; font-weight:900;}
    .cover-btn.playing::after{content:"Ⅱ"; background:var(--accent);}
    .cover-btn.paused::after{content:"▶"; background:var(--accent);}
    .title-cell{min-width:0; overflow:hidden;}
    .title-link{font-weight:950; color:var(--text); text-decoration:none; line-height:1.32; display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
    .subtle{font-size:11.5px; color:var(--muted); line-height:1.35; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
    .creator-link{color:var(--muted); text-decoration:none;}
    .style-cell{overflow:hidden;}
    .style-tags{display:flex; gap:4px; overflow:hidden; white-space:nowrap;}
    .style-tag{max-width:62px; border:1px solid var(--line); background:#fff; color:#4b5563; border-radius:999px; padding:3px 6px; font-size:10.5px; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
    .style-empty{font-size:12px; color:var(--muted)}
    .stat-stack{display:flex; flex-direction:column; align-items:flex-end; gap:3px; font-variant-numeric:tabular-nums;}
    .like-btn{border:1px solid var(--line2); background:#fff; color:var(--text); border-radius:999px; padding:5px 8px; font-size:12px; font-weight:900; cursor:pointer; white-space:nowrap; min-width:72px;}
    .like-btn.active{background:#e7eee2; color:var(--accent-dark); border-color:var(--accent);}
    .mini-stat-line{font-size:11px; color:var(--muted); white-space:nowrap;}
    .rank-info-btn,.select-btn,.small-btn,.cloud-playlist-save,.ghost-btn{border:1px solid var(--line2); background:#fff; color:var(--text); border-radius:10px; padding:7px 8px; cursor:pointer; font-size:12px; font-weight:900; white-space:nowrap;}
    .rank-info-btn:hover,.select-btn:hover,.small-btn:hover,.ghost-btn:hover{border-color:var(--accent); color:var(--accent-dark);}
    .select-btn.selected{background:var(--accent); border-color:var(--accent); color:#fff;}
    .playlist-bottom{border-top:1px solid var(--line); padding:10px 12px; background:rgba(255,253,248,.94);}
    .playlist-bottom-row{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;}
    .selected-summary{font-size:12px; color:var(--muted);}
    .save-panel{display:none; margin-top:10px; border:1px solid var(--line); background:#fff; border-radius:14px; padding:10px;}
    .save-panel.show{display:block;}
    .save-grid{display:grid; grid-template-columns:1fr auto auto; gap:8px; align-items:center;}
    .cloud-playlist-input{min-width:0; border:1px solid var(--line2); border-radius:999px; padding:9px 12px; font-size:13px; outline:none;}
    .cloud-playlist-save{background:var(--accent); border-color:var(--accent); color:#fff; border-radius:999px; padding:9px 12px;}
    .cloud-playlist-save:disabled,.ghost-btn:disabled{opacity:.55; cursor:not-allowed;}
    .cloud-playlist-status{margin-top:7px; min-height:16px; color:var(--muted); font-size:11.5px;}
    .now-cover-wrap{width:100%; aspect-ratio:1/1; max-height:310px; border-radius:18px; overflow:hidden; background:#e5e0d8; margin-bottom:12px; flex:0 0 auto;}
    .now-cover{width:100%; height:100%; object-fit:cover; display:block;}
    .now-placeholder{width:100%; height:100%; display:grid; place-items:center; color:var(--muted); font-size:13px;}
    .now-title{font-size:21px; font-weight:1000; line-height:1.22; margin-bottom:4px; word-break:break-word;}
    .now-creator{font-size:13px; color:var(--muted); margin-bottom:7px; word-break:break-word;}
    .now-style-tags{display:flex; flex-wrap:wrap; gap:5px; min-height:20px; margin-bottom:8px;}
    .now-style-tag{max-width:112px; border:1px solid var(--line); background:#fff; color:#4b5563; border-radius:999px; padding:3px 8px; font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
    .progress-wrap{margin:8px 0;}
    input[type="range"]{width:100%; accent-color:var(--accent);}
    .time-row{display:flex; justify-content:space-between; color:var(--muted); font-size:11px; margin-top:4px;}
    .control-row{display:flex; align-items:center; justify-content:center; gap:8px; margin:9px 0;}
    .ctrl-btn{border:1px solid var(--line2); background:#fff; color:var(--text); border-radius:999px; min-width:38px; height:38px; cursor:pointer; font-weight:900;}
    .ctrl-btn.main{background:var(--accent); color:#fff; border-color:var(--accent); min-width:48px; height:48px;}
    .mode-actions{display:grid; grid-template-columns:repeat(5,1fr); gap:6px; margin:4px 0 10px;}
    .small-btn{padding:7px 4px; font-size:11px;}
    .small-btn.active{background:#e7eee2; color:var(--accent-dark); border-color:var(--accent);}
    .volume-row{display:grid; grid-template-columns:54px 1fr 42px; gap:8px; align-items:center; font-size:12px; color:var(--muted); margin:6px 0 8px;}
    .loudness-row{display:grid; grid-template-columns:1fr auto; gap:8px; align-items:center; font-size:11px; color:var(--muted); margin-bottom:10px;}
    .loudness-status{min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
    .loudness-btn{border:1px solid var(--line2); background:#fff; color:var(--text); border-radius:999px; padding:5px 7px; cursor:pointer; font-size:11px; font-weight:900; white-space:nowrap;}
    .loudness-btn.active{background:#e7eee2; color:var(--accent-dark); border-color:var(--accent);}
    .lyrics-panel{margin-top:auto; border:1px solid var(--line); background:#fff; border-radius:14px; padding:11px; flex:1 1 260px; min-height:260px; overflow-y:auto; white-space:pre-wrap; font-size:12px; line-height:1.48; color:#374151;}
    .lyrics-panel.empty{color:var(--muted);}
    .footer-credit{padding:10px 12px; text-align:center; font-size:11px; color:var(--muted);}
    .modal-backdrop{position:fixed; inset:0; background:rgba(36,33,30,.34); display:none; align-items:center; justify-content:center; z-index:50; padding:18px;}
    .modal-backdrop.show{display:flex;}
    .modal-card{width:min(720px,96vw); max-height:86vh; overflow:auto; background:#fffdf8; border:1px solid var(--line); border-radius:18px; box-shadow:0 24px 80px rgba(0,0,0,.25); padding:18px;}
    .modal-head{display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:12px;}
    .modal-title{font-size:20px; font-weight:1000;}.modal-sub{font-size:12px; color:var(--muted); margin-top:3px;}
    .modal-close{border:0; background:#f1eadf; width:34px; height:34px; border-radius:999px; cursor:pointer; font-size:20px;}
    .score-grid{display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:12px 0;}
    .score-box{border:1px solid var(--line); background:#fff; border-radius:12px; padding:10px;}.score-label{color:var(--muted); font-size:11px;}.score-value{font-size:17px; font-weight:1000; font-variant-numeric:tabular-nums;}
    .detail-grid{display:grid; grid-template-columns:1fr 1fr; gap:8px;}.detail-item{border:1px solid var(--line); border-radius:12px; padding:9px; font-size:12px;}.detail-label{font-size:10px; color:var(--muted); margin-bottom:3px;}
    @media(max-width:1050px){.app-shell{grid-template-columns:1fr; height:auto; overflow:visible}.ranking-panel,.player-panel{height:auto}.table-wrap{max-height:680px}.lyrics-panel{min-height:200px}.search-input{min-width:180px}.score-grid,.detail-grid{grid-template-columns:repeat(2,1fr)}}
    </style>

    <div class="app-shell" id="appShell">
      <main class="ranking-panel">
        <div class="ranking-topbar">
          <div>
            <div class="rank-view-tabs" id="rankViewTabs"></div>
            <div class="ranking-title" id="rankingTitle">__TITLE_HTML__</div>
            <div class="ranking-sub" id="rankingSub">__SUBTITLE_HTML__</div>
          </div>
          <input class="search-input" id="searchInput" placeholder="Search title / style / creator">
        </div>
        <div class="table-wrap">
          <table class="song-table">
            <colgroup>
              <col style="width:44px"><col style="width:62px"><col><col style="width:150px"><col style="width:132px"><col style="width:54px"><col style="width:56px">
            </colgroup>
            <thead>
              <tr>
                <th class="sortable" data-sort-key="rank" style="text-align:right;">순위<span class="sort-indicator"></span></th>
                <th class="sortable" data-sort-key="has_image">앨범<span class="sort-indicator"></span></th>
                <th class="sortable" data-sort-key="title">곡 정보<span class="sort-indicator"></span></th>
                <th class="sortable" data-sort-key="style_tags">스타일<span class="sort-indicator"></span></th>
                <th class="sortable" data-sort-key="upvote_count" style="text-align:right;">반응<span class="sort-indicator"></span></th>
                <th style="text-align:center;">상세</th>
                <th style="text-align:center;">선택</th>
              </tr>
            </thead>
            <tbody id="songTableBody"></tbody>
          </table>
        </div>
        <div class="playlist-bottom">
          <div class="playlist-bottom-row">
            <div class="selected-summary" id="selectedSummary">선택된 곡 0개</div>
            <div>
              <button class="ghost-btn" id="clearSelectedBtn">선택 해제</button>
              <button class="cloud-playlist-save" id="openSaveSelectedBtn">선택곡 플레이리스트 저장</button>
            </div>
          </div>
          <div class="save-panel" id="saveSelectedPanel">
            <div class="save-grid">
              <input class="cloud-playlist-input" id="cloudPlaylistName" placeholder="플레이리스트 이름">
              <button class="cloud-playlist-save" id="cloudSavePlaylistBtn">저장</button>
              <button class="ghost-btn" id="cancelSaveSelectedBtn">취소</button>
            </div>
            <div class="cloud-playlist-status" id="cloudPlaylistStatus">곡을 선택한 뒤 저장하세요.</div>
          </div>
        </div>
        <div class="footer-credit">Busy Chart</div>
      </main>

      <aside class="player-panel">
        <div class="now-cover-wrap" id="nowCoverWrap"><div class="now-placeholder">No track selected</div></div>
        <div class="now-title" id="nowTitle">곡을 선택하세요</div>
        <div class="now-creator" id="nowCreator">앨범 이미지를 누르면 재생됩니다.</div>
        <div class="now-style-tags" id="nowStyleTags"></div>
        <div class="progress-wrap">
          <input id="progress" type="range" min="0" max="1000" value="0">
          <div class="time-row"><span id="currentTime">0:00</span><span id="duration">0:00</span></div>
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
        <div class="volume-row"><span>Volume</span><input id="volume" type="range" min="0" max="100" value="80"><span id="volumeText">80%</span></div>
        <div class="loudness-row"><span class="loudness-status" id="loudnessStatus">LUFS 정규화 꺼짐</span><button class="loudness-btn" id="loudnessNormalizeBtn">-14 LUFS OFF</button></div>
        <div class="lyrics-panel empty" id="lyricsPanel">가사/프롬프트 정보가 있으면 여기에 표시됩니다.</div>
      </aside>
    </div>

    <div class="modal-backdrop" id="rankingModal">
      <div class="modal-card">
        <div class="modal-head"><div><div class="modal-title" id="modalTitle">Detailed Info</div><div class="modal-sub" id="modalSub"></div></div><button class="modal-close" id="modalCloseBtn">×</button></div>
        <div class="score-grid"><div class="score-box"><div class="score-label">Trend</div><div class="score-value" id="scoreTrend">0</div></div><div class="score-box"><div class="score-label">Base</div><div class="score-value" id="scoreBase">0</div></div><div class="score-box"><div class="score-label">Play</div><div class="score-value" id="scoreGrowth">0</div></div><div class="score-box"><div class="score-label">Freshness</div><div class="score-value" id="scoreFreshness">0</div></div></div>
        <div class="detail-grid" id="detailGrid"></div>
      </div>
    </div>

    <script>
    const initialSongs = __SONGS_JSON__;
    const tabsData = __TABS_JSON__;
    const tabsOrder = __TABS_ORDER_JSON__;
    const defaultTabKey = __DEFAULT_TAB_KEY_JS__;
    const cloudConfig = __CLOUD_CONFIG_JSON__;
    let songs = Array.isArray(initialSongs) ? initialSongs : [];
    let currentTabKey = defaultTabKey || (Array.isArray(tabsOrder) && tabsOrder[0]) || "";
    let currentViewRows = [];
    let playlist = [];
    let currentIndex = -1;
    let selectedIds = new Set();
    let sortState = {key:null, direction:null};
    let repeatOne=false, repeatAll=true, playbackMode="sequence", loudnessNormalize=false;
    let audio = new Audio();
    let busyRecordedPlayIds = new Set();
    let busySessionId = String((cloudConfig && cloudConfig.sessionId) || window.localStorage.getItem("busyChart.sessionId") || "");
    if(!busySessionId){ busySessionId = `${Date.now()}-${Math.random().toString(16).slice(2)}`; window.localStorage.setItem("busyChart.sessionId", busySessionId); }

    const $ = id => document.getElementById(id);
    const songTableBody=$('songTableBody'), searchInput=$('searchInput'), rankViewTabs=$('rankViewTabs'), rankingTitle=$('rankingTitle'), rankingSub=$('rankingSub');
    const nowCoverWrap=$('nowCoverWrap'), nowTitle=$('nowTitle'), nowCreator=$('nowCreator'), nowStyleTags=$('nowStyleTags'), lyricsPanel=$('lyricsPanel');
    const playBtn=$('playBtn'), prevBtn=$('prevBtn'), nextBtn=$('nextBtn'), repeatOneBtn=$('repeatOneBtn'), repeatAllBtn=$('repeatAllBtn'), sequenceBtn=$('sequenceBtn'), shuffleBtn=$('shuffleBtn'), clearBtn=$('clearBtn');
    const volume=$('volume'), volumeText=$('volumeText'), loudnessNormalizeBtn=$('loudnessNormalizeBtn'), loudnessStatus=$('loudnessStatus'), progress=$('progress'), currentTimeEl=$('currentTime'), durationEl=$('duration');
    const selectedSummary=$('selectedSummary'), openSaveSelectedBtn=$('openSaveSelectedBtn'), saveSelectedPanel=$('saveSelectedPanel'), cloudPlaylistName=$('cloudPlaylistName'), cloudSavePlaylistBtn=$('cloudSavePlaylistBtn'), cancelSaveSelectedBtn=$('cancelSaveSelectedBtn'), clearSelectedBtn=$('clearSelectedBtn'), cloudPlaylistStatus=$('cloudPlaylistStatus');
    const rankingModal=$('rankingModal'), modalCloseBtn=$('modalCloseBtn'), modalTitle=$('modalTitle'), modalSub=$('modalSub'), scoreTrend=$('scoreTrend'), scoreBase=$('scoreBase'), scoreGrowth=$('scoreGrowth'), scoreFreshness=$('scoreFreshness'), detailGrid=$('detailGrid');

    function esc(v){return String(v==null?'':v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
    function num(n){try{return Number(n||0).toLocaleString()}catch(e){return '0'}}
    function fl(n,d=2){try{return Number(n||0).toFixed(d)}catch(e){return '0.00'}}
    function fmtTime(sec){ if(!isFinite(sec)||sec<0)return '0:00'; const m=Math.floor(sec/60), s=Math.floor(sec%60); return `${m}:${String(s).padStart(2,'0')}`; }
    function getSongById(id){ return allKnownSongs().get(String(id)); }
    function allKnownSongs(){ const m=new Map(); (songs||[]).forEach(s=>{if(s&&s.id)m.set(String(s.id),s)}); if(tabsData&&typeof tabsData==='object'){Object.values(tabsData).forEach(t=>(Array.isArray(t&&t.songs)?t.songs:[]).forEach(s=>{if(s&&s.id&&!m.has(String(s.id)))m.set(String(s.id),s)}));} return m; }
    function currentTab(){ return tabsData && currentTabKey && tabsData[currentTabKey] ? tabsData[currentTabKey] : {title:'Chart',description:'',songs:songs}; }
    function compactSong(song){ return {id:String(song.id||''),title:song.title||'',creator:song.creator||'',handle:song.handle||'',style_tags:song.style_tags||'',audio_url:song.audio_url||'',image_url:song.image_url||'',lyrics:song.lyrics||'',integrated_lufs:song.integrated_lufs,true_peak_db:song.true_peak_db,loudness_gain_db:song.loudness_gain_db}; }
    function styleTags(value){ const parts=String(value||'').split(',').map(x=>x.trim()).filter(Boolean).slice(0,3); if(!parts.length)return '<span class="style-empty">-</span>'; return `<div class="style-tags">${parts.map(p=>`<span class="style-tag" title="${esc(p)}">${esc(p)}</span>`).join('')}</div>`; }
    function nowTags(value){ const parts=String(value||'').split(',').map(x=>x.trim()).filter(Boolean).slice(0,5); nowStyleTags.innerHTML = parts.length ? parts.map(p=>`<span class="now-style-tag" title="${esc(p)}">${esc(p)}</span>`).join('') : '<span class="style-empty">스타일 정보 없음</span>'; }
    function sortable(song,key){ if(key==='rank')return Number(song.rank||0); if(key==='has_image')return song.image_url?1:0; if(key==='title')return String(song.title||'').toLowerCase(); if(key==='style_tags')return String(song.style_tags||'').toLowerCase(); if(key==='upvote_count')return Number(song.upvote_count||0); if(key==='play_count')return Number(song.play_count||0); if(key==='comment_count')return Number(song.comment_count||0); return ''; }
    function sortRows(list){ if(!sortState.key)return list.slice().sort((a,b)=>Number(a.rank||0)-Number(b.rank||0)); return list.slice().sort((a,b)=>{const av=sortable(a,sortState.key), bv=sortable(b,sortState.key); let r=(typeof av==='number'&&typeof bv==='number')?av-bv:String(av).localeCompare(String(bv),'ko',{numeric:true,sensitivity:'base'}); if(r===0)r=Number(a.rank||0)-Number(b.rank||0); return sortState.direction==='asc'?r:-r;}); }
    function updateSortIndicators(){document.querySelectorAll('th.sortable').forEach(th=>{const ind=th.querySelector('.sort-indicator'); if(!ind)return; ind.textContent=(sortState.key===th.dataset.sortKey&&sortState.direction)?(sortState.direction==='asc'?' ▲':' ▼'):'';});}
    function cycleSort(key){ if(sortState.key!==key){sortState={key,direction:'desc'};} else if(sortState.direction==='desc'){sortState.direction='asc';} else {sortState={key:null,direction:null};} renderTable(searchInput.value||''); }

    function renderTabs(){ if(!rankViewTabs)return; const keys=(Array.isArray(tabsOrder)&&tabsOrder.length?tabsOrder:Object.keys(tabsData||{})); rankViewTabs.innerHTML=keys.map(k=>{const t=tabsData[k]||{}; return `<button class="rank-view-tab ${k===currentTabKey?'active':''}" data-tab="${esc(k)}">${esc(t.title||k)}</button>`}).join(''); rankViewTabs.querySelectorAll('[data-tab]').forEach(btn=>btn.onclick=()=>{currentTabKey=btn.dataset.tab; renderTable(searchInput.value||'');}); }
    function renderTable(filterText=''){
      const tab=currentTab(); songs=Array.isArray(tab.songs)?tab.songs:[]; rankingTitle.textContent=tab.title||'__TITLE_HTML__'; rankingSub.textContent=tab.description||'__SUBTITLE_HTML__'; renderTabs();
      const q=String(filterText||'').trim().toLowerCase(); let rows=songs.filter(s=>!q||[s.title,s.style_tags,s.creator,s.handle,s.id].join(' ').toLowerCase().includes(q)); rows=sortRows(rows).slice(0,200); currentViewRows=rows;
      updateSortIndicators(); if(!rows.length){songTableBody.innerHTML='<tr><td colspan="7" style="padding:22px;text-align:center;color:var(--muted)">표시할 곡이 없습니다.</td></tr>'; return;}
      songTableBody.innerHTML=rows.map(song=>{
        const img=song.image_url?`<img class="cover" src="${esc(song.image_url)}" loading="lazy">`:'<div class="cover"></div>';
        const selected=selectedIds.has(String(song.id));
        return `<tr data-song-id="${esc(song.id)}">
          <td class="rank">${esc(song.rank||'')}</td>
          <td><button class="cover-btn" data-action="cover" data-song-id="${esc(song.id)}">${img}</button></td>
          <td class="title-cell"><span class="title-link">${esc(song.title||'Untitled')}</span><div class="subtle">${esc(song.creator||'Unknown')} · ${esc(song.created_at||'')}</div></td>
          <td class="style-cell">${styleTags(song.style_tags)}</td>
          <td><div class="stat-stack"><button class="like-btn ${song.liked?'active':''}" data-action="like" data-song-id="${esc(song.id)}">♥ <span>${num(song.upvote_count)}</span></button><div class="mini-stat-line">▶ ${num(song.play_count)} · 💬 ${num(song.comment_count)}</div></div></td>
          <td style="text-align:center"><button class="rank-info-btn" data-action="info" data-song-id="${esc(song.id)}">정보</button></td>
          <td style="text-align:center"><button class="select-btn ${selected?'selected':''}" data-action="select" data-song-id="${esc(song.id)}">${selected?'✓':'선택'}</button></td>
        </tr>`;
      }).join('');
      bindTableEvents(); refreshCovers(); updateSelectedSummary();
    }
    function bindTableEvents(){
      songTableBody.querySelectorAll('[data-action="cover"]').forEach(b=>b.onclick=e=>{e.preventDefault(); coverClick(b.dataset.songId);});
      songTableBody.querySelectorAll('[data-action="like"]').forEach(b=>b.onclick=e=>{e.preventDefault(); toggleSongLikeRemote(b.dataset.songId,b);});
      songTableBody.querySelectorAll('[data-action="info"]').forEach(b=>b.onclick=e=>{e.preventDefault(); openInfo(b.dataset.songId);});
      songTableBody.querySelectorAll('[data-action="select"]').forEach(b=>b.onclick=e=>{e.preventDefault(); toggleSelected(b.dataset.songId);});
    }
    function toggleSelected(id){ const key=String(id); if(selectedIds.has(key)) selectedIds.delete(key); else selectedIds.add(key); renderTable(searchInput.value||''); }
    function updateSelectedSummary(){ selectedSummary.textContent=`선택된 곡 ${selectedIds.size}개`; }
    function clearSelected(){ selectedIds.clear(); saveSelectedPanel.classList.remove('show'); renderTable(searchInput.value||''); }
    function openSavePanel(){ if(!selectedIds.size){alert('먼저 차트에서 곡을 선택하세요.'); return;} saveSelectedPanel.classList.add('show'); cloudPlaylistName.focus(); }
    function cancelSavePanel(){ saveSelectedPanel.classList.remove('show'); }
    function cloudEnabled(){ return Boolean(cloudConfig&&cloudConfig.enabled&&cloudConfig.supabaseUrl&&cloudConfig.anonKey&&cloudConfig.playlistToken); }
    async function callRpc(fn,body){ const res=await fetch(`${String(cloudConfig.supabaseUrl).replace(/[/]$/,'')}/rest/v1/rpc/${fn}`,{method:'POST',headers:{apikey:cloudConfig.anonKey,Authorization:`Bearer ${cloudConfig.anonKey}`,'Content-Type':'application/json'},body:JSON.stringify(body||{})}); const text=await res.text(); let data=null; if(text){try{data=JSON.parse(text)}catch(e){data=text}} if(!res.ok)throw new Error((data&&data.message)||text||res.statusText); return data; }
    async function saveSelectedPlaylist(){ if(!selectedIds.size){alert('선택된 곡이 없습니다.'); return;} if(!cloudEnabled()){cloudPlaylistStatus.textContent=(cloudConfig&&cloudConfig.message)||'로그인 후 저장할 수 있습니다.'; return;} const name=String(cloudPlaylistName.value||'').trim()||`Busy Playlist ${new Date().toLocaleString()}`; try{cloudSavePlaylistBtn.disabled=true; cloudPlaylistStatus.textContent=`저장 중: ${name}`; const ids=Array.from(selectedIds); const result=await callRpc('cloud_save_playlist',{p_token:cloudConfig.playlistToken,p_name:name,p_song_ids:ids}); cloudPlaylistStatus.textContent=`'${name}' 저장 완료 · ${Number(result&&result.song_count||ids.length)}곡`; cloudPlaylistName.value=''; selectedIds.clear(); renderTable(searchInput.value||'');}catch(e){console.warn(e); cloudPlaylistStatus.textContent=`저장 실패: ${e.message||e}`;}finally{cloudSavePlaylistBtn.disabled=false;} }
    function likeApiEnabled(){return Boolean(cloudConfig&&cloudConfig.likeEnabled&&cloudConfig.supabaseUrl&&cloudConfig.anonKey&&cloudConfig.sessionId)}
    async function toggleSongLikeRemote(songId,button){ const song=getSongById(songId); if(!song||!likeApiEnabled()){alert('좋아요 기능 설정을 확인하세요.');return;} try{button.disabled=true; const r=await callRpc('bc_toggle_song_like',{p_song_id:songId,p_actor_key:String(cloudConfig.sessionId)}); song.liked=Boolean(r&&r.liked); if(r&&typeof r.like_count!=='undefined') song.upvote_count=Number(r.like_count)||0; renderTable(searchInput.value||'');}catch(e){console.warn(e);alert('좋아요 처리에 실패했습니다.')}finally{button.disabled=false;} }
    function buildPlayQueueFromView(){ playlist=currentViewRows.filter(s=>s&&s.audio_url).map(compactSong); }
    function getCurrentSong(){ return playlist[currentIndex]||null; }
    function isCurrentSong(song){ const c=getCurrentSong(); return c&&song&&String(c.id)===String(song.id); }
    function coverClick(id){ const rows=currentViewRows.filter(s=>s&&s.audio_url); if(!rows.length){alert('재생 가능한 곡이 없습니다.');return;} playlist=rows.map(compactSong); const idx=playlist.findIndex(s=>String(s.id)===String(id)); if(idx<0){alert('이 곡에는 음원 URL이 없습니다.');return;} if(currentIndex===idx){togglePlay();}else{currentIndex=idx; loadCurrent(true);} }
    function loadCurrent(autoplay=false){ const s=getCurrentSong(); if(!s)return; audio.src=s.audio_url; audio.load(); updateNowPlaying(); updateVolume(); if(autoplay) audio.play().catch(()=>{}); refreshCovers(); }
    function updateNowPlaying(){ const s=getCurrentSong(); if(!s){nowCoverWrap.innerHTML='<div class="now-placeholder">No track selected</div>'; nowTitle.textContent='곡을 선택하세요'; nowCreator.textContent='앨범 이미지를 누르면 재생됩니다.'; lyricsPanel.textContent='가사/프롬프트 정보가 있으면 여기에 표시됩니다.'; lyricsPanel.classList.add('empty'); nowStyleTags.innerHTML=''; return;} nowCoverWrap.innerHTML=s.image_url?`<img class="now-cover" src="${esc(s.image_url)}">`:'<div class="now-placeholder">No cover</div>'; nowTitle.textContent=s.title||'Untitled'; nowCreator.textContent=s.creator||''; nowTags(s.style_tags); lyricsPanel.textContent=s.lyrics||'가사 정보가 없습니다.'; lyricsPanel.classList.toggle('empty',!s.lyrics); }
    function togglePlay(){ if(!getCurrentSong()){ const first=(currentViewRows||[]).find(s=>s.audio_url); if(first)coverClick(first.id); return;} if(audio.paused)audio.play().catch(()=>{}); else audio.pause(); }
    function playNext(){ if(!playlist.length)return; if(playbackMode==='shuffle'){currentIndex=Math.floor(Math.random()*playlist.length);} else if(currentIndex<playlist.length-1){currentIndex++;} else if(repeatAll){currentIndex=0;} else return; loadCurrent(true); }
    function playPrev(){ if(!playlist.length)return; if(currentIndex>0)currentIndex--; else if(repeatAll)currentIndex=playlist.length-1; loadCurrent(true); }
    function dbToGain(db){return Math.pow(10,Number(db||0)/20)}
    function currentGainDb(){ const s=getCurrentSong(); return s && isFinite(Number(s.loudness_gain_db)) ? Number(s.loudness_gain_db) : 0; }
    function updateLoudnessUi(){ loudnessNormalizeBtn.classList.toggle('active',loudnessNormalize); loudnessNormalizeBtn.textContent=loudnessNormalize?'-14 LUFS ON':'-14 LUFS OFF'; const s=getCurrentSong(); loudnessStatus.textContent=s&&s.integrated_lufs!=null?`gain ${fl(currentGainDb(),1)} dB · ${fl(s.integrated_lufs,1)} LUFS · ${fl(s.true_peak_db,1)} dBTP`:'LUFS 분석값 없음'; }
    function updateVolume(){ const user=Number(volume.value||80)/100; volumeText.textContent=`${Math.round(user*100)}%`; audio.volume=Math.min(1,Math.max(0,user*(loudnessNormalize?dbToGain(currentGainDb()):1))); updateLoudnessUi(); }
    async function recordPlayIfNeeded(){ const s=getCurrentSong(); if(!s||!s.id||busyRecordedPlayIds.has(String(s.id)))return; if(!audio.duration||audio.duration<10)return; if((audio.currentTime/audio.duration)<0.30)return; busyRecordedPlayIds.add(String(s.id)); if(!(cloudConfig&&cloudConfig.playRecordEnabled&&cloudConfig.supabaseUrl&&cloudConfig.anonKey))return; try{await callRpc('bc_record_play',{p_song_id:String(s.id),p_session_id:busySessionId,p_play_seconds:Math.floor(audio.currentTime||0)}); s.play_count=Number(s.play_count||0)+1; renderTable(searchInput.value||'');}catch(e){console.warn('play record failed',e);} }
    function refreshCovers(){ document.querySelectorAll('.cover-btn[data-song-id]').forEach(c=>{ const s=getSongById(c.dataset.songId); c.classList.remove('playing','paused'); if(s&&isCurrentSong(s)){c.classList.add(audio.paused?'paused':'playing');}}); playBtn.textContent=audio.paused?'▶':'Ⅱ'; }
    function openInfo(id){ const s=getSongById(id); if(!s)return; modalTitle.textContent=s.title||'Untitled'; modalSub.textContent=`${s.creator||''} · ${s.created_at||''}`; scoreTrend.textContent=fl(s.trend_score); scoreBase.textContent=fl(s.base_score); scoreGrowth.textContent=num(s.play_count); scoreFreshness.textContent=fl(s.freshness_score); detailGrid.innerHTML=[['재생',num(s.play_count)],['좋아요',num(s.upvote_count)],['댓글',num(s.comment_count)],['LUFS',s.integrated_lufs==null?'N/A':fl(s.integrated_lufs,1)],['True Peak',s.true_peak_db==null?'N/A':fl(s.true_peak_db,1)],['스타일',s.style_tags||'-']].map(([k,v])=>`<div class="detail-item"><div class="detail-label">${esc(k)}</div><div>${esc(v)}</div></div>`).join(''); rankingModal.classList.add('show'); }
    function bindSort(){ document.querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>cycleSort(th.dataset.sortKey)); }
    function init(){ renderTabs(); bindSort(); renderTable(''); updateNowPlaying(); refreshCovers(); updateVolume(); }

    searchInput.addEventListener('input',()=>renderTable(searchInput.value||''));
    openSaveSelectedBtn.addEventListener('click',openSavePanel); cancelSaveSelectedBtn.addEventListener('click',cancelSavePanel); cloudSavePlaylistBtn.addEventListener('click',saveSelectedPlaylist); clearSelectedBtn.addEventListener('click',clearSelected);
    playBtn.addEventListener('click',togglePlay); nextBtn.addEventListener('click',playNext); prevBtn.addEventListener('click',playPrev); volume.addEventListener('input',updateVolume); loudnessNormalizeBtn.addEventListener('click',()=>{loudnessNormalize=!loudnessNormalize;updateVolume();});
    repeatOneBtn.addEventListener('click',()=>{repeatOne=!repeatOne;if(repeatOne)repeatAll=false; repeatOneBtn.classList.toggle('active',repeatOne); repeatAllBtn.classList.toggle('active',repeatAll);});
    repeatAllBtn.addEventListener('click',()=>{repeatAll=!repeatAll;if(repeatAll)repeatOne=false; repeatAllBtn.classList.toggle('active',repeatAll); repeatOneBtn.classList.toggle('active',repeatOne);});
    sequenceBtn.addEventListener('click',()=>{playbackMode='sequence'; sequenceBtn.classList.add('active'); shuffleBtn.classList.remove('active');});
    shuffleBtn.addEventListener('click',()=>{playbackMode='shuffle'; shuffleBtn.classList.add('active'); sequenceBtn.classList.remove('active');});
    clearBtn.addEventListener('click',()=>{audio.pause(); currentIndex=-1; playlist=[]; updateNowPlaying(); refreshCovers();});
    progress.addEventListener('input',()=>{ if(audio.duration) audio.currentTime=(Number(progress.value||0)/1000)*audio.duration; });
    audio.addEventListener('play',refreshCovers); audio.addEventListener('pause',refreshCovers); audio.addEventListener('ended',()=>{ if(repeatOne){audio.currentTime=0; audio.play().catch(()=>{});} else playNext(); });
    audio.addEventListener('timeupdate',()=>{ if(audio.duration){progress.value=String(Math.round((audio.currentTime/audio.duration)*1000)); durationEl.textContent=fmtTime(audio.duration);} currentTimeEl.textContent=fmtTime(audio.currentTime); recordPlayIfNeeded(); });
    audio.addEventListener('loadedmetadata',()=>{ durationEl.textContent=fmtTime(audio.duration); });
    modalCloseBtn.addEventListener('click',()=>rankingModal.classList.remove('show')); rankingModal.addEventListener('click',e=>{if(e.target===rankingModal)rankingModal.classList.remove('show')});
    init();
    </script>
    """

    html_rendered = (html_template
        .replace("__TITLE_HTML__", title_html)
        .replace("__SUBTITLE_HTML__", subtitle_html)
        .replace("__SONGS_JSON__", songs_json)
        .replace("__TABS_JSON__", tabs_json)
        .replace("__TABS_ORDER_JSON__", tabs_order_json)
        .replace("__DEFAULT_TAB_KEY_JS__", default_tab_key_js)
        .replace("__CLOUD_CONFIG_JSON__", cloud_config_json)
    )
    components.html(html_rendered, height=1060, scrolling=False)
