from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List

import streamlit as st

from app_modules.player_component import render_player_ranking_html
from app_modules.busy_supabase import (
    MAX_AUDIO_MB,
    MAX_COVER_MB,
    add_comment,
    add_song_to_playlist,
    create_playlist,
    create_song,
    delete_playlist,
    delete_song,
    ensure_profile,
    get_playlist_songs,
    get_public_config,
    get_session_id,
    get_song,
    get_user_id,
    is_logged_in,
    is_login_available,
    is_supabase_ready,
    liked_song_ids,
    list_comments,
    list_my_playlists,
    list_my_songs,
    list_public_playlists,
    list_songs,
    remove_song_from_playlist,
    toggle_comment_like,
    toggle_song_like,
    update_profile,
    update_song,
)

st.set_page_config(page_title="Busy Chart v1.0", page_icon="🎧", layout="wide", initial_sidebar_state="collapsed")

APP_TITLE = "Busy Chart v1.0"

# -----------------------------
# UI helpers
# -----------------------------

def rerun():
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


def inject_css():
    st.markdown(
        """
        <style>
        #MainMenu {visibility:hidden;} footer {visibility:hidden;}
        header[data-testid="stHeader"] {height:0rem; background:transparent;}
        header[data-testid="stHeader"] * {display:none;}
        [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton {display:none !important;}
        :root {
          --bc-bg:#fbf8f1; --bc-card:#fffdf8; --bc-card2:#f7f1e7; --bc-line:#e7ddd0;
          --bc-text:#24211e; --bc-muted:#7b7167; --bc-accent:#6f7f63; --bc-accent-dark:#2f3a2f;
          --bc-soft:#f1eadf; --bc-sage:#e7eee2;
        }
        html, body, [data-testid="stAppViewContainer"] {
          background: radial-gradient(circle at 8% 0%, rgba(225,214,201,.72), transparent 30%),
                      radial-gradient(circle at 92% 8%, rgba(206,217,201,.55), transparent 28%),
                      linear-gradient(180deg, #faf7f1 0%, #f5f1e9 55%, #f8f6f1 100%) !important;
          color:var(--bc-text);
        }
        .block-container {padding-top:.9rem; padding-bottom:3rem; max-width:1460px;}
        .bc-topbar {display:flex; align-items:center; justify-content:space-between; gap:18px; border:1px solid rgba(231,221,208,.95); border-radius:18px; padding:12px 14px; background:rgba(255,253,248,.84); backdrop-filter:blur(18px); box-shadow:0 16px 42px rgba(72,60,47,.08); margin-bottom:12px;}
        .bc-brand {display:flex; align-items:center; gap:11px;}
        .bc-logo {width:38px; height:38px; border-radius:12px; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#e7ddd0,#cfdac9); color:#2c2925; font-weight:1000; box-shadow:0 8px 20px rgba(88,76,61,.13);}
        .bc-brand-title {font-size:22px; font-weight:1000; letter-spacing:-.045em; line-height:1; color:#24211e;}
        .bc-brand-sub {font-size:12px; color:var(--bc-muted); margin-top:4px;}
        .bc-status {font-size:12px; color:var(--bc-muted); text-align:right;}
        .bc-card {border:1px solid var(--bc-line); border-radius:18px; padding:16px; background:rgba(255,253,248,.88); box-shadow:0 12px 32px rgba(72,60,47,.055);}
        .bc-title {font-size:24px; font-weight:1000; letter-spacing:-.04em; margin:10px 0 4px;}
        .bc-sub {font-size:13px; color:var(--bc-muted); margin-bottom:12px;}
        .bc-mini {font-size:12px; color:var(--bc-muted);}
        .bc-profile-row {display:flex; align-items:center; gap:10px; justify-content:flex-end;}
        .bc-avatar {width:32px; height:32px; border-radius:999px; object-fit:cover; background:#efe6db;}
        div[data-testid="stHorizontalBlock"] button[kind="primary"], div[data-testid="stHorizontalBlock"] button[kind="secondary"], [data-testid="stPopover"] button {border-radius:10px !important; min-height:38px; box-shadow:none !important; border:1px solid #e4d8c8 !important;}
        div[data-testid="stHorizontalBlock"] button[kind="primary"] {background:#2f3a2f !important; color:#fffdf8 !important;}
        div[data-testid="stHorizontalBlock"] button[kind="secondary"], [data-testid="stPopover"] button {background:rgba(255,253,248,.72) !important; color:#5a5148 !important;}
        button {font-weight:750 !important;}
        .stTextInput input, .stTextArea textarea, .stSelectbox div, .stFileUploader {border-radius:12px;}
        @media (max-width:900px){.block-container{padding-left:.75rem; padding-right:.75rem}.bc-topbar{display:block}.bc-status{text-align:left;margin-top:10px}.bc-brand-title{font-size:20px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def set_page(page: str):
    st.session_state["bc_page"] = page
    rerun()


def current_page() -> str:
    return st.session_state.get("bc_page", "chart")


def render_menu_button(label: str, page: str, type_page: str = "secondary"):
    if st.button(label, use_container_width=True, type="primary" if current_page() == page else type_page, key=f"nav_{page}"):
        set_page(page)


def render_header():
    profile = ensure_profile() if is_logged_in() else None
    display_name = (profile or {}).get("display_name") or (profile or {}).get("email") or "Guest"
    avatar_url = (profile or {}).get("avatar_url") or ""
    status = "서버 연결됨" if is_supabase_ready() else "서버 설정 필요"
    mode = "Creator" if is_logged_in() else "Guest"
    avatar_html = f'<img class="bc-avatar" src="{html.escape(avatar_url)}">' if avatar_url else '<div class="bc-avatar"></div>'
    st.markdown(
        f"""
        <div class="bc-topbar">
          <div class="bc-brand">
            <div class="bc-logo">B</div>
            <div><div class="bc-brand-title">Busy Chart</div><div class="bc-brand-sub">v1.0</div></div>
          </div>
          <div class="bc-status"><div class="bc-profile-row">{avatar_html}<b>{html.escape(display_name)}</b></div>{status} · {mode}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns([1, 1, 1, 1.1, 3], gap="small")
    with cols[0]: render_menu_button("차트", "chart")
    with cols[1]: render_menu_button("플레이리스트", "playlists")
    with cols[2]: render_menu_button("AI 큐레이션", "ai")
    with cols[3]:
        if is_logged_in():
            try:
                with st.popover("내 아이디", use_container_width=True):
                    if st.button("프로필 수정", use_container_width=True): set_page("profile")
                    if st.button("새 곡 업로드", use_container_width=True): set_page("upload")
                    if st.button("업로드 관리", use_container_width=True): set_page("manage")
                    st.divider()
                    if st.button("로그아웃", use_container_width=True):
                        st.logout()
            except Exception:
                render_menu_button("내 아이디", "profile")
        else:
            if st.button("로그인", use_container_width=True, type="secondary"):
                try: st.login()
                except Exception as exc: st.error(f"로그인 설정 확인: {exc}")


def format_dt(value: str) -> str:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(value or "")[:19]


def song_artist(song: Dict[str, Any]) -> str:
    prof = song.get("bc_profiles") or {}
    return song.get("artist_name") or prof.get("display_name") or "Unknown"


def to_float(v, default=0.0):
    try:
        if v is None or v == "": return default
        return float(v)
    except Exception:
        return default


def song_payload(song: Dict[str, Any], rank: int) -> Dict[str, Any]:
    return {
        "rank": rank,
        "rank_change": None,
        "rank_status": "",
        "previous_rank": None,
        "current_rank_saved": None,
        "id": str(song.get("id") or ""),
        "title": str(song.get("title") or "Untitled"),
        "creator": song_artist(song),
        "handle": "",
        "created_at": format_dt(song.get("created_at")),
        "created_at_raw": song.get("created_at") or "",
        "style_tags": song.get("style_tags") or "",
        "play_count": int(song.get("play_count") or 0),
        "upvote_count": int(song.get("like_count") or 0),
        "comment_count": int(song.get("comment_count") or 0),
        "effective_comment_count": int(song.get("comment_count") or 0),
        "adjusted_comment_count": int(song.get("comment_count") or 0),
        "comment_quality_ratio": 1.0,
        "is_outlier": False,
        "outlier_reasons": "",
        "song_url": "",
        "audio_url": song.get("audio_url") or "",
        "image_url": song.get("cover_url") or "",
        "lyrics": song.get("lyrics") or song.get("description") or "",
        "integrated_lufs": to_float(song.get("integrated_lufs"), None),
        "true_peak_db": to_float(song.get("true_peak_db"), None),
        "loudness_gain_db": to_float(song.get("loudness_gain_db"), None),
        "loudness_target_lufs": to_float(song.get("loudness_target_lufs"), -14.0),
        "loudness_true_peak_ceiling_db": to_float(song.get("loudness_true_peak_ceiling_db"), -1.0),
        "loudness_status": song.get("loudness_status") or "",
        "trend_score": to_float(song.get("trend_score"), 0.0),
        "base_score": round(math.log1p(int(song.get("play_count") or 0)) + 3 * math.log1p(int(song.get("like_count") or 0)) + 4 * math.log1p(int(song.get("comment_count") or 0)), 6),
        "growth_score": 0.0,
        "freshness_score": 0.0,
        "growth_score_raw": 0.0,
        "play_delta_window": 0.0,
        "upvote_delta_window": 0.0,
        "comment_delta_window": 0.0,
        "freshness": 0.0,
        "age_hours": 0.0,
    }


def make_tab(songs: List[Dict[str, Any]], title: str, description: str) -> Dict[str, Any]:
    return {"title": title, "description": description, "count": len(songs), "songs": [song_payload(s, i+1) for i, s in enumerate(songs)], "histories": {}}


def build_tabs() -> tuple[Dict[str, Dict], List[str]]:
    trending = list_songs(300, order="score")
    newest = list_songs(300, order="new")
    liked = list_songs(300, order="liked")
    played = list_songs(300, order="played")
    tabs = {
        "trending": make_tab(trending, "Trending", "앱 내부 재생·좋아요·댓글 기반 차트"),
        "new": make_tab(newest, "New Uploads", "최근 업로드된 곡"),
        "liked": make_tab(liked, "Most Liked", "좋아요가 많은 곡"),
        "played": make_tab(played, "Most Played", "재생수가 많은 곡"),
    }
    return tabs, ["trending", "new", "liked", "played"]


def ranking_config_json():
    return json.dumps({
        "play_weight": 1.0,
        "like_weight": 3.0,
        "comment_weight": 4.0,
        "growth_weight": 0.0,
        "freshness_weight": 30.0,
        "freshness_power": 1.25,
    }, ensure_ascii=False)


def render_old_chart_component():
    tabs, order = build_tabs()
    tabs_json = json.dumps(tabs, ensure_ascii=False).replace("</", "<\\/")
    order_json = json.dumps(order, ensure_ascii=False).replace("</", "<\\/")
    first = tabs["trending"]
    songs_json = json.dumps(first["songs"], ensure_ascii=False).replace("</", "<\\/")
    public_cfg = get_public_config()
    cloud_cfg = {
        "enabled": False,
        "playerEnabled": bool(is_logged_in()),
        "playRecordEnabled": True,
        "supabaseUrl": public_cfg.get("supabase_url", ""),
        "anonKey": public_cfg.get("supabase_anon_key", ""),
        "sessionId": get_session_id(),
        "message": "플레이리스트는 상단 메뉴에서 관리합니다.",
    }
    render_player_ranking_html(
        songs_json,
        "{}",
        ranking_config_json(),
        title="Busy Chart",
        subtitle="앨범 이미지를 누르면 재생/일시정지됩니다.",
        tabs_json=tabs_json,
        tabs_order_json=order_json,
        default_tab_key="trending",
        cloud_config_json=json.dumps(cloud_cfg, ensure_ascii=False).replace("</", "<\\/"),
    )


def render_chart():
    if not is_supabase_ready():
        st.warning("Supabase 설정을 확인하세요.")
    render_old_chart_component()
    render_community_panel()


def render_community_panel():
    songs = list_songs(100, order="score")
    if not songs:
        return
    st.markdown("<div class='bc-title'>곡 커뮤니티</div><div class='bc-sub'>좋아요, 댓글, 플레이리스트 추가는 여기에서 관리합니다.</div>", unsafe_allow_html=True)
    options = {f"{i+1}. {s.get('title') or 'Untitled'} · {song_artist(s)}": str(s.get("id")) for i, s in enumerate(songs)}
    selected_label = st.selectbox("곡 선택", list(options.keys()), label_visibility="collapsed")
    song_id = options[selected_label]
    song = get_song(song_id) or {}
    liked = song_id in liked_song_ids([song_id])
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        if st.button("♥ 좋아요 취소" if liked else "♥ 좋아요", use_container_width=True):
            toggle_song_like(song_id); rerun()
    with c2:
        if is_logged_in():
            pls = list_my_playlists()
            if pls:
                pl_map = {p.get("name"): p.get("id") for p in pls}
                name = st.selectbox("플레이리스트", list(pl_map.keys()), label_visibility="collapsed", key="add_pl_select")
                if st.button("＋ 추가", use_container_width=True):
                    add_song_to_playlist(pl_map[name], song_id); st.success("추가됨")
            else:
                st.caption("내 플레이리스트가 없습니다.")
        else:
            st.caption("플레이리스트는 로그인 후 사용")
    with c3:
        st.caption(f"▶ {song.get('play_count') or 0} · ♥ {song.get('like_count') or 0} · 💬 {song.get('comment_count') or 0}")

    with st.expander("댓글", expanded=False):
        comments = list_comments(song_id)
        for cm in comments:
            st.markdown(f"**{html.escape(cm.get('display_name') or 'User')}** · {format_dt(cm.get('created_at'))}")
            st.write(cm.get("body") or "")
            if st.button(f"댓글 좋아요 {cm.get('like_count') or 0}", key=f"cm_like_{cm.get('id')}"):
                toggle_comment_like(str(cm.get("id"))); rerun()
            st.divider()
        if is_logged_in():
            body = st.text_area("댓글 작성", max_chars=500, key=f"comment_body_{song_id}")
            if st.button("댓글 등록", key=f"comment_submit_{song_id}"):
                if add_comment(song_id, body):
                    st.success("등록됨"); rerun()
        else:
            st.caption("댓글 작성은 로그인 후 가능합니다.")


def render_profile():
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    profile = ensure_profile() or {}
    st.markdown("<div class='bc-title'>프로필 수정</div>", unsafe_allow_html=True)
    with st.form("profile_form"):
        display_name = st.text_input("닉네임", value=profile.get("display_name") or "")
        email = st.text_input("이메일", value=profile.get("email") or "", disabled=True)
        avatar = st.file_uploader("아바타 이미지", type=["jpg","jpeg","png","webp"])
        bio = st.text_area("소개", value=profile.get("bio") or "", max_chars=500)
        c1, c2 = st.columns(2)
        with c1:
            suno_url = st.text_input("Suno 링크", value=profile.get("suno_url") or "")
            spotify_url = st.text_input("Spotify 링크", value=profile.get("spotify_url") or "")
            youtube_url = st.text_input("YouTube 링크", value=profile.get("youtube_url") or "")
        with c2:
            instagram_url = st.text_input("Instagram 링크", value=profile.get("instagram_url") or "")
            website_url = st.text_input("Website / Link hub", value=profile.get("website_url") or "")
        if st.form_submit_button("저장", type="primary"):
            if update_profile(display_name, avatar, bio, suno_url, spotify_url, youtube_url, instagram_url, website_url):
                st.success("저장됨"); rerun()


def render_upload():
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    st.markdown("<div class='bc-title'>새 곡 업로드</div><div class='bc-sub'>MP3와 앨범 이미지를 업로드하면 바로 차트에 반영됩니다.</div>", unsafe_allow_html=True)
    with st.form("upload_form", clear_on_submit=True):
        title = st.text_input("노래 제목")
        style_tags = st.text_input("스타일태그 / 장르", placeholder="예: AI pop, hard psy, lo-fi")
        description = st.text_area("곡 소개", max_chars=2000)
        lyrics = st.text_area("가사", height=220)
        audio = st.file_uploader(f"음원 파일 · MP3 · 최대 {MAX_AUDIO_MB}MB", type=["mp3"])
        cover = st.file_uploader(f"앨범 이미지 · JPG/PNG/WEBP · 최대 {MAX_COVER_MB}MB", type=["jpg","jpeg","png","webp"])
        comments_enabled = st.checkbox("댓글 허용", value=True)
        rights = st.checkbox("이 음원을 업로드하고 공개/공유/재생할 권리를 가지고 있음을 확인합니다.")
        if st.form_submit_button("업로드", type="primary"):
            if not rights:
                st.error("권리 확인 동의가 필요합니다.")
            else:
                song_id = create_song(title, style_tags, lyrics, audio, cover, comments_enabled, description=description)
                if song_id:
                    st.success("업로드 완료. 차트에 반영되었습니다.")
                    st.session_state["bc_page"] = "chart"
                    rerun()


def render_manage():
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    st.markdown("<div class='bc-title'>업로드 관리</div>", unsafe_allow_html=True)
    if st.button("＋ 새 곡 업로드", type="primary"):
        set_page("upload")
    songs = list_my_songs()
    if not songs:
        st.info("아직 업로드한 곡이 없습니다.")
        return
    for s in songs:
        with st.expander(f"{s.get('title')} · {format_dt(s.get('created_at'))}"):
            with st.form(f"edit_{s.get('id')}"):
                title = st.text_input("제목", value=s.get("title") or "")
                style_tags = st.text_input("스타일태그", value=s.get("style_tags") or "")
                description = st.text_area("곡 소개", value=s.get("description") or "")
                lyrics = st.text_area("가사", value=s.get("lyrics") or "", height=180)
                comments_enabled = st.checkbox("댓글 허용", value=bool(s.get("comments_enabled", True)))
                visibility = st.selectbox("공개 상태", ["public", "private"], index=0 if s.get("visibility") == "public" else 1)
                new_cover = st.file_uploader("앨범 이미지 교체", type=["jpg","jpeg","png","webp"], key=f"cover_{s.get('id')}")
                new_audio = st.file_uploader("음원 교체", type=["mp3"], key=f"audio_{s.get('id')}")
                col1, col2 = st.columns(2)
                with col1:
                    save = st.form_submit_button("수정 저장", type="primary")
                with col2:
                    delete = st.form_submit_button("삭제")
                if save:
                    ok = update_song(str(s.get("id")), {"title": title, "style_tags": style_tags, "description": description, "lyrics": lyrics, "comments_enabled": comments_enabled, "visibility": visibility, "status":"active"}, new_cover, new_audio)
                    if ok: st.success("저장됨"); rerun()
                if delete:
                    if delete_song(str(s.get("id"))): st.success("삭제됨"); rerun()


def render_playlists():
    st.markdown("<div class='bc-title'>플레이리스트</div>", unsafe_allow_html=True)
    if is_logged_in():
        with st.expander("새 플레이리스트 만들기", expanded=False):
            with st.form("new_playlist"):
                name = st.text_input("이름")
                desc = st.text_area("설명")
                visibility = st.selectbox("공개 상태", ["public", "private"])
                if st.form_submit_button("생성", type="primary"):
                    pid = create_playlist(name, desc, visibility)
                    if pid: st.success("생성됨"); rerun()
        my = list_my_playlists()
        if my:
            st.markdown("#### 내 플레이리스트")
            for p in my:
                with st.expander(p.get("name") or "Untitled"):
                    st.caption(p.get("description") or "")
                    songs = get_playlist_songs(str(p.get("id")))
                    for s in songs:
                        c1, c2 = st.columns([4,1])
                        with c1: st.write(f"{s.get('title')} · {song_artist(s)}")
                        with c2:
                            if st.button("제거", key=f"rm_{p.get('id')}_{s.get('id')}"):
                                remove_song_from_playlist(str(p.get("id")), str(s.get("id"))); rerun()
                    if st.button("플레이리스트 삭제", key=f"delpl_{p.get('id')}"):
                        delete_playlist(str(p.get("id"))); rerun()
    public = list_public_playlists()
    if public:
        st.markdown("#### 공개 플레이리스트")
        for p in public:
            st.markdown(f"<div class='bc-card'><b>{html.escape(p.get('name') or 'Untitled')}</b><br><span class='bc-mini'>{html.escape(p.get('description') or '')}</span></div>", unsafe_allow_html=True)


def render_ai():
    st.markdown("<div class='bc-title'>AI 큐레이션</div><div class='bc-sub'>현재 업로드된 곡의 태그와 설명을 바탕으로 플레이리스트 초안을 만듭니다.</div>", unsafe_allow_html=True)
    songs = list_songs(200, order="score")
    theme = st.text_input("원하는 분위기", placeholder="예: 새벽 감성, 운동용, hard psy, 비 오는 날")
    count = st.slider("곡 수", 5, 30, 12)
    if st.button("큐레이션 만들기", type="primary"):
        if not songs:
            st.warning("등록된 곡이 없습니다.")
        else:
            terms = [t.strip().lower() for t in theme.replace(",", " ").split() if t.strip()]
            def score(s):
                text = f"{s.get('title','')} {s.get('style_tags','')} {s.get('description','')}".lower()
                return sum(1 for t in terms if t in text) + float(s.get("trend_score") or 0) / 100
            picked = sorted(songs, key=score, reverse=True)[:count]
            st.session_state["ai_picked"] = [str(s.get("id")) for s in picked]
    picked_ids = st.session_state.get("ai_picked") or []
    if picked_ids:
        by_id = {str(s.get("id")): s for s in songs}
        picked = [by_id[i] for i in picked_ids if i in by_id]
        for i, s in enumerate(picked, 1):
            st.write(f"{i}. {s.get('title')} · {song_artist(s)}")
        if is_logged_in():
            name = st.text_input("저장할 플레이리스트 이름", value=theme or "AI Curated Playlist")
            if st.button("플레이리스트로 저장"):
                pid = create_playlist(name, f"AI 큐레이션: {theme}", "public")
                if pid:
                    for s in picked:
                        add_song_to_playlist(pid, str(s.get("id")))
                    st.success("저장됨")
        else:
            st.caption("저장은 로그인 후 가능합니다.")


def main():
    inject_css()
    render_header()
    if not is_login_available():
        st.caption("Streamlit 로그인 API를 사용할 수 없습니다. streamlit>=1.42가 필요합니다.")
    page = current_page()
    if page == "chart": render_chart()
    elif page == "playlists": render_playlists()
    elif page == "ai": render_ai()
    elif page == "profile": render_profile()
    elif page == "upload": render_upload()
    elif page == "manage": render_manage()
    else: render_chart()

if __name__ == "__main__":
    main()
