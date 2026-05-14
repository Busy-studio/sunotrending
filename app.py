from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Dict, List

import streamlit as st

from app_modules.busy_player import render_audio_tracker
from app_modules.busy_supabase import (
    MAX_AUDIO_MB,
    MAX_COVER_MB,
    add_comment,
    delete_song,
    ensure_profile,
    get_auth_user,
    get_public_config,
    get_session_id,
    get_song,
    get_supabase_client,
    get_user_id,
    has_bad_words,
    is_logged_in,
    is_login_available,
    is_supabase_ready,
    liked_song_ids,
    list_comments,
    list_my_songs,
    list_songs,
    toggle_comment_like,
    toggle_song_like,
    update_profile,
    update_song,
    create_song,
)

st.set_page_config(
    page_title="Busy Chart v1.0",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_TITLE = "Busy Chart v1.0"


def inject_css():
    st.markdown(
        """
        <style>
        /* Hide Streamlit chrome as much as possible for a standalone platform look */
        #MainMenu {visibility:hidden;}
        footer {visibility:hidden;}
        header[data-testid="stHeader"] {height:0rem; background: transparent;}
        header[data-testid="stHeader"] * {display:none;}
        [data-testid="stToolbar"] {display:none !important;}
        [data-testid="stDecoration"] {display:none !important;}
        [data-testid="stStatusWidget"] {display:none !important;}
        .stDeployButton {display:none !important;}

        :root {
          --busy-bg:#f7f3ec;
          --busy-card:#fffdf8;
          --busy-card-2:#fbf7ef;
          --busy-line:#e7ddd0;
          --busy-text:#23211f;
          --busy-muted:#7b7167;
          --busy-accent:#6f7f63;
          --busy-accent-2:#9a7665;
          --busy-accent-3:#6d7690;
          --busy-soft:#efe6db;
          --busy-hover:#f1eadf;
        }
        html, body, [data-testid="stAppViewContainer"] {
          background:
            radial-gradient(circle at 8% 0%, rgba(225,214,201,.72), transparent 30%),
            radial-gradient(circle at 92% 8%, rgba(206,217,201,.55), transparent 28%),
            linear-gradient(180deg, #faf7f1 0%, #f5f1e9 52%, #f8f6f1 100%) !important;
          color:var(--busy-text);
        }
        .block-container {padding-top: .9rem; padding-bottom: 3rem; max-width: 1440px;}
        .busy-topbar {
          display:flex; align-items:center; justify-content:space-between; gap:18px;
          border:1px solid rgba(231,221,208,.95); border-radius:18px; padding:12px 14px;
          background:rgba(255,253,248,.82); backdrop-filter:blur(18px);
          box-shadow:0 16px 42px rgba(72,60,47,.08); margin-bottom:14px;
        }
        .busy-brand {display:flex; align-items:center; gap:11px;}
        .busy-logo {width:38px; height:38px; border-radius:12px; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#e7ddd0,#cfdac9); color:#2c2925; font-weight:1000; box-shadow:0 8px 20px rgba(88,76,61,.13);}
        .busy-brand-title {font-size:22px; font-weight:1000; letter-spacing:-.04em; line-height:1; color:#24211e;}
        .busy-brand-sub {font-size:12px; color:var(--busy-muted); margin-top:4px;}
        .busy-status {font-size:12px; color:var(--busy-muted); text-align:right;}
        .busy-hero {border:1px solid rgba(231,221,208,.95); border-radius:24px; padding:24px; background:linear-gradient(135deg,#fffdf8 0%,#f1eadf 48%,#e7eee2 100%); color:#24211e; margin:14px 0 18px; box-shadow:0 18px 50px rgba(72,60,47,.075);}
        .busy-hero-title {font-size:30px; font-weight:1000; letter-spacing:-.05em; line-height:1;}
        .busy-hero-sub {font-size:13px; color:#766c61; margin-top:8px;}
        .busy-user-chip {display:flex; align-items:center; justify-content:flex-end; gap:8px; font-size:13px; color:#24211e; font-weight:800;}
        .busy-avatar-sm {width:28px; height:28px; border-radius:999px; object-fit:cover; background:#efe6db;}
        .busy-section-title {font-size:22px; font-weight:950; letter-spacing:-.03em; margin:14px 0 10px; color:#24211e;}
        .busy-page-subtitle {font-size:13px; color:var(--busy-muted); margin-top:-5px; margin-bottom:12px;}
        .busy-card {border:1px solid rgba(231,221,208,.95); border-radius:18px; padding:15px; background:rgba(255,253,248,.86); height:100%; box-shadow:0 8px 24px rgba(72,60,47,.055);}
        .busy-chart-head {display:grid; grid-template-columns:58px 76px minmax(240px,1fr) 230px 210px; gap:12px; align-items:center; padding:10px 16px; border-bottom:1px solid #e7ddd0; color:#8a7d70; font-size:11px; font-weight:900; text-transform:uppercase; letter-spacing:.08em;}
        .busy-chart-row {display:grid; grid-template-columns:58px 76px minmax(240px,1fr) 230px 210px; gap:12px; align-items:center; padding:12px 16px; border-bottom:1px solid rgba(231,221,208,.82); transition:background .16s ease, transform .16s ease;}
        .busy-chart-row:hover {background:rgba(241,234,223,.62);}
        .busy-chart-row:last-child {border-bottom:0;}
        .busy-rank {font-size:16px; font-weight:1000; color:#776b60; text-align:center;}
        .busy-rank.hot {color:#2f3a2f;}
        .busy-cover-img {width:64px; height:64px; object-fit:cover; border-radius:14px; background:#f2ece2; display:block; box-shadow:0 8px 20px rgba(72,60,47,.10);}
        .busy-track-title {font-weight:1000; font-size:15px; line-height:1.22; color:#24211e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        .busy-track-artist {font-size:12px; color:#6f655b; margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        .busy-track-tags {font-size:11px; color:#94877a; margin-top:5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        .busy-stats {font-size:12px; color:#51483f; display:flex; gap:7px; flex-wrap:wrap; justify-content:flex-start;}
        .busy-pill {display:inline-flex; align-items:center; gap:4px; border:1px solid #e7ddd0; border-radius:999px; padding:4px 9px; background:#fbf7ef; font-weight:750;}
        .busy-actions {display:flex; gap:7px;}
        .busy-now-playing {border:1px solid rgba(231,221,208,.95); border-radius:20px; padding:14px; background:rgba(255,253,248,.88); box-shadow:0 10px 28px rgba(72,60,47,.06); margin:12px 0 16px;}
        [data-testid="stVerticalBlockBorderWrapper"] {border-color:#e7ddd0 !important; border-radius:18px !important; background:rgba(255,253,248,.78) !important; box-shadow:0 8px 22px rgba(72,60,47,.045) !important;}
        [data-testid="stVerticalBlockBorderWrapper"]:hover {background:rgba(251,247,239,.9) !important;}
        .busy-muted {color:var(--busy-muted); font-size:12px;}
        .busy-divider {height:1px; background:#e7ddd0; margin:16px 0;}

        /* Website-like menu buttons */
        div[data-testid="stHorizontalBlock"] button[kind="secondary"],
        div[data-testid="stHorizontalBlock"] button[kind="primary"] {
          border-radius:10px !important;
          min-height:38px;
          box-shadow:none !important;
          border:1px solid #e4d8c8 !important;
        }
        div[data-testid="stHorizontalBlock"] button[kind="primary"] {
          background:#2f3a2f !important;
          color:#fffdf8 !important;
        }
        div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
          background:rgba(255,253,248,.72) !important;
          color:#5a5148 !important;
        }
        div[data-testid="stHorizontalBlock"] button:hover {
          border-color:#c9bba8 !important;
          background:var(--busy-hover) !important;
          color:#24211e !important;
        }
        button {font-weight:750 !important;}

        [data-testid="stPopover"] button {
          border-radius:10px !important;
          border:1px solid #e4d8c8 !important;
          background:rgba(255,253,248,.72) !important;
          color:#5a5148 !important;
        }
        [data-testid="stPopover"] button:hover {
          background:var(--busy-hover) !important;
          color:#24211e !important;
        }
        @media (max-width: 900px) {
          .block-container {padding-left:.75rem; padding-right:.75rem;}
          .busy-topbar {display:block;}
          .busy-status {text-align:left; margin-top:10px;}
          .busy-brand-title {font-size:20px;}
          .busy-chart-head {display:none;}
          .busy-chart-row {grid-template-columns:46px 64px minmax(0,1fr); gap:10px; padding:12px; margin-bottom:10px; border:1px solid #e7ddd0; border-radius:18px; background:rgba(255,253,248,.86); box-shadow:0 8px 22px rgba(72,60,47,.055);}
          .busy-chart-row > div:nth-child(4), .busy-chart-row > div:nth-child(5) {grid-column:3 / 4;}
          .busy-cover-img {width:58px; height:58px; border-radius:13px;}
          .busy-stats {margin-top:7px;}
        }
        @media (max-width: 520px) {
          .busy-chart-row {grid-template-columns:38px 58px minmax(0,1fr);}
          .busy-rank {font-size:14px;}
          .busy-track-title {font-size:14px;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def rerun():
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


def render_header():
    profile = ensure_profile() if is_logged_in() else {}
    display_name = (profile or {}).get("display_name") or (profile or {}).get("email") or "Guest"
    avatar_url = (profile or {}).get("avatar_url") or ""
    status_text = "Online" if is_supabase_ready() else "Setup required"
    auth_text = "Creator mode" if is_logged_in() else "Guest mode"
    avatar_html = f'<img class="busy-avatar-sm" src="{html.escape(avatar_url)}">' if avatar_url else '<div class="busy-avatar-sm"></div>'
    st.markdown(
        f"""
        <div class="busy-topbar">
          <div class="busy-brand">
            <div class="busy-logo">B</div>
            <div>
              <div class="busy-brand-title">Busy Chart</div>
              <div class="busy-brand-sub">v1.0</div>
            </div>
          </div>
          <div class="busy-status">{status_text}<br>{auth_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_nav_buttons()


def format_date(value: str) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(value)[:19]


def song_artist(song: Dict) -> str:
    prof = song.get("bc_profiles") or {}
    return song.get("artist_name") or prof.get("display_name") or "Unknown"


def render_song_row(song: Dict, rank: int, liked: bool):
    song_id = str(song.get("id"))
    cover = song.get("cover_url") or ""
    title = song.get("title") or "Untitled"
    artist = song_artist(song)
    tags = song.get("style_tags") or ""
    uploaded = format_date(song.get("created_at"))

    with st.container(border=True):
        cols = st.columns([0.45, 0.8, 3.4, 1.55, 1.75], gap="small", vertical_alignment="center")
        with cols[0]:
            rank_color = "#2f3a2f" if rank <= 3 else "#776b60"
            st.markdown(f"<div class='busy-rank' style='color:{rank_color}'>#{rank}</div>", unsafe_allow_html=True)
        with cols[1]:
            if cover:
                st.markdown(f"<img class='busy-cover-img' src='{html.escape(cover)}' onerror='this.style.opacity=.12'>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='busy-cover-img'></div>", unsafe_allow_html=True)
        with cols[2]:
            st.markdown(
                f"""
                <div class="busy-track-title">{html.escape(title)}</div>
                <div class="busy-track-artist">{html.escape(artist)}</div>
                <div class="busy-track-tags">{html.escape(tags[:140])}</div>
                """,
                unsafe_allow_html=True,
            )
        with cols[3]:
            st.markdown(
                f"""
                <div class="busy-stats">
                  <span class="busy-pill">▶ {int(song.get('play_count') or 0)}</span>
                  <span class="busy-pill">♥ {int(song.get('like_count') or 0)}</span>
                  <span class="busy-pill">💬 {int(song.get('comment_count') or 0)}</span>
                </div>
                <div class="busy-muted" style="margin-top:7px;">{html.escape(uploaded[:16])}</div>
                """,
                unsafe_allow_html=True,
            )
        with cols[4]:
            b1, b2 = st.columns([1, 1], gap="small")
            with b1:
                if st.button("재생", key=f"play_{song_id}", use_container_width=True, type="primary" if st.session_state.get("selected_song_id") == song_id else "secondary"):
                    st.session_state["selected_song_id"] = song_id
                    st.session_state["show_song_detail"] = False
                    rerun()
            with b2:
                if st.button("상세", key=f"detail_{song_id}", use_container_width=True):
                    st.session_state["selected_song_id"] = song_id
                    st.session_state["show_song_detail"] = True
                    rerun()
            if st.button("♥ 좋아요" if not liked else "♥ 취소", key=f"like_{song_id}", use_container_width=True):
                toggle_song_like(song_id)
                rerun()


def render_now_playing(song_id: str):
    song = get_song(song_id)
    if not song:
        return
    title = song.get("title") or "Untitled"
    artist = song_artist(song)
    st.markdown(
        f"""
        <div class="busy-now-playing">
          <div class="busy-muted">재생 중</div>
          <div class="busy-track-title">{html.escape(title)}</div>
          <div class="busy-track-artist">{html.escape(artist)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_audio_tracker(
        song_id=str(song.get("id")),
        audio_url=song.get("audio_url") or "",
        title=title,
        cover_url=song.get("cover_url") or "",
        public_config=get_public_config(),
        session_id=get_session_id(),
        height=106,
    )


def render_chart():
    st.markdown("""
        <div class='busy-hero'>
          <div class='busy-hero-title'>Busy Chart</div>
          <div class='busy-hero-sub'>새로운 업로드와 지금 많이 듣는 곡.</div>
        </div>
        """, unsafe_allow_html=True)
    controls = st.columns([1.1, .9, 2.8], gap="small")
    with controls[0]:
        order_label = st.selectbox("정렬", ["트렌딩", "최신", "좋아요", "재생수"], label_visibility="collapsed")
    with controls[1]:
        limit = st.selectbox("표시", [50, 100, 200, 300], index=0, label_visibility="collapsed")
    order_map = {"트렌딩": "score", "최신": "new", "좋아요": "liked", "재생수": "played"}
    songs = list_songs(limit=limit, order=order_map[order_label])
    if not songs:
        st.markdown("<div class='busy-card busy-muted'>아직 등록된 곡이 없습니다.</div>", unsafe_allow_html=True)
        return

    selected = st.session_state.get("selected_song_id")
    if selected:
        render_now_playing(selected)

    liked = liked_song_ids([str(s.get("id")) for s in songs])
    st.markdown(
        """
        <div class="busy-chart-head"><div>순위</div><div>커버</div><div>곡</div><div>반응</div><div>액션</div></div>
        """,
        unsafe_allow_html=True,
    )
    for idx, song in enumerate(songs, start=1):
        render_song_row(song, idx, str(song.get("id")) in liked)

    selected = st.session_state.get("selected_song_id")
    if selected and st.session_state.get("show_song_detail"):
        st.markdown("<div class='busy-divider'></div>", unsafe_allow_html=True)
        render_song_detail(selected)


def render_song_detail(song_id: str):
    song = get_song(song_id)
    if not song:
        st.warning("곡을 찾을 수 없습니다.")
        return
    title = song.get("title") or "Untitled"
    st.markdown(f"<div class='busy-section-title'>{html.escape(title)}</div>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.3], gap="large")
    with left:
        if song.get("cover_url"):
            st.image(song.get("cover_url"), use_container_width=True)
        render_audio_tracker(
            song_id=str(song.get("id")),
            audio_url=song.get("audio_url") or "",
            title=title,
            cover_url=song.get("cover_url") or "",
            public_config=get_public_config(),
            session_id=get_session_id(),
            height=112,
        )
        if st.button("♥ 좋아요 / 취소", key=f"detail_like_{song_id}", use_container_width=True):
            toggle_song_like(song_id)
            rerun()
    with right:
        st.caption(f"아티스트: {song_artist(song)}")
        st.caption(f"업로드: {format_date(song.get('created_at'))}")
        st.write(song.get("description") or "")
        if song.get("style_tags"):
            st.markdown(f"**스타일태그**: {song.get('style_tags')}")
        with st.expander("가사", expanded=False):
            st.text(song.get("lyrics") or "")
    render_comments(song)


def render_comments(song: Dict):
    song_id = str(song.get("id"))
    st.markdown("<div class='busy-section-title'>댓글</div>", unsafe_allow_html=True)
    if not song.get("comments_enabled", True):
        st.info("이 곡은 댓글 작성이 비활성화되어 있습니다.")
    elif is_logged_in():
        with st.form(f"comment_form_{song_id}", clear_on_submit=True):
            body = st.text_area("댓글", max_chars=500, placeholder="500자 이하로 작성하세요. 비속어/혐오 표현은 제한됩니다.")
            submitted = st.form_submit_button("댓글 등록")
            if submitted:
                if add_comment(song_id, body):
                    st.success("댓글이 등록되었습니다.")
                    rerun()
    else:
        st.caption("댓글은 로그인한 사용자만 작성할 수 있습니다. 좋아요는 비로그인도 가능합니다.")
    comments = list_comments(song_id)
    if not comments:
        st.caption("아직 댓글이 없습니다.")
        return
    for c in comments:
        with st.container(border=True):
            st.markdown(f"**{html.escape(c.get('display_name') or 'Busy User')}** · {format_date(c.get('created_at'))}")
            st.write(c.get("body") or "")
            if st.button(f"댓글 좋아요 ♥ {int(c.get('like_count') or 0)}", key=f"comment_like_{c.get('id')}"):
                toggle_comment_like(str(c.get("id")))
                rerun()


def render_profile_page():
    st.markdown("<div class='busy-section-title'>프로필</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    profile = ensure_profile() or {}
    left, right = st.columns([1, 2.2], gap="large")
    with left:
        if profile.get("avatar_url"):
            st.image(profile.get("avatar_url"), width=180)
        else:
            st.markdown("<div class='busy-card busy-muted'>아바타 없음</div>", unsafe_allow_html=True)
        if profile.get("email"):
            st.caption(f"이메일: {profile.get('email')}")
    with right:
        with st.form("profile_form"):
            display_name = st.text_input("닉네임", value=profile.get("display_name") or "", max_chars=80)
            bio = st.text_area("소개", value=profile.get("bio") or "", max_chars=500, placeholder="간단한 소개를 입력하세요.")
            avatar = st.file_uploader("아바타 이미지", type=["jpg", "jpeg", "png", "webp"])
            st.markdown("**외부 링크**")
            suno_url = st.text_input("Suno 링크", value=profile.get("suno_url") or "", placeholder="https://suno.com/@...")
            spotify_url = st.text_input("Spotify 링크", value=profile.get("spotify_url") or "", placeholder="https://open.spotify.com/artist/...")
            youtube_url = st.text_input("YouTube 링크", value=profile.get("youtube_url") or "", placeholder="https://youtube.com/@...")
            instagram_url = st.text_input("Instagram 링크", value=profile.get("instagram_url") or "", placeholder="https://instagram.com/...")
            website_url = st.text_input("Website / Link hub", value=profile.get("website_url") or "", placeholder="https://...")
            submitted = st.form_submit_button("프로필 저장")
            if submitted:
                if update_profile(
                    display_name=display_name,
                    avatar_file=avatar,
                    bio=bio,
                    suno_url=suno_url,
                    spotify_url=spotify_url,
                    youtube_url=youtube_url,
                    instagram_url=instagram_url,
                    website_url=website_url,
                ):
                    st.success("프로필이 저장되었습니다.")
                    rerun()


def render_upload_page():
    st.markdown("<div class='busy-section-title'>업로드</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("업로드는 로그인 후 사용할 수 있습니다.")
        return
    ensure_profile()
    st.markdown(f"<div class='busy-page-subtitle'>MP3 up to {MAX_AUDIO_MB}MB · Cover image up to {MAX_COVER_MB}MB</div>", unsafe_allow_html=True)
    with st.form("upload_form"):
        title = st.text_input("노래 제목 *", max_chars=160)
        style_tags = st.text_input("스타일태그 / 장르", placeholder="예: hard psy, vocal chop, synth-pop", max_chars=300)
        description = st.text_area("곡 소개", max_chars=2000)
        lyrics = st.text_area("가사", height=180, max_chars=20000)
        audio = st.file_uploader("음원 파일 *", type=["mp3"])
        cover = st.file_uploader("앨범 이미지 *", type=["jpg", "jpeg", "png", "webp"])
        comments_enabled = st.checkbox("댓글 허용", value=True)
        rights = st.checkbox("업로드 및 공개 재생 권한을 확인합니다.")
        submitted = st.form_submit_button("곡 등록")
        if submitted:
            if not rights:
                st.error("권리 확인 동의가 필요합니다.")
            elif has_bad_words(title + style_tags + description):
                st.error("입력 내용에 제한된 표현이 포함되어 있습니다.")
            else:
                song_id = create_song(title, style_tags, lyrics, audio, cover, comments_enabled, description)
                if song_id:
                    st.success("업로드 완료")
                    st.session_state["selected_song_id"] = song_id


def render_manage_page():
    st.markdown("<div class='busy-section-title'>업로드 관리</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    songs = list_my_songs()
    if st.button("+ 새 곡 업로드"):
        st.session_state["busy_nav"] = "Upload"
        rerun()
    if not songs:
        st.markdown("<div class='busy-card busy-muted'>아직 업로드한 곡이 없습니다.</div>", unsafe_allow_html=True)
        return
    for song in songs:
        with st.expander(f"{song.get('title')} · {song.get('visibility')} · {song.get('status')}"):
            left, right = st.columns([1, 2])
            with left:
                if song.get("cover_url"):
                    st.image(song.get("cover_url"), use_container_width=True)
                st.caption(f"▶ {song.get('play_count',0)} · ♥ {song.get('like_count',0)} · 💬 {song.get('comment_count',0)}")
            with right:
                with st.form(f"edit_{song.get('id')}"):
                    title = st.text_input("제목", value=song.get("title") or "", key=f"title_{song.get('id')}")
                    style_tags = st.text_input("스타일태그", value=song.get("style_tags") or "", key=f"tags_{song.get('id')}")
                    description = st.text_area("곡 소개", value=song.get("description") or "", key=f"desc_{song.get('id')}")
                    lyrics = st.text_area("가사", value=song.get("lyrics") or "", height=120, key=f"lyrics_{song.get('id')}")
                    comments_enabled = st.checkbox("댓글 허용", value=bool(song.get("comments_enabled", True)), key=f"ce_{song.get('id')}")
                    visibility = st.selectbox("공개 상태", ["public", "private"], index=0 if song.get("visibility") == "public" else 1, key=f"vis_{song.get('id')}")
                    new_cover = st.file_uploader("앨범 이미지 교체", type=["jpg", "jpeg", "png", "webp"], key=f"cover_{song.get('id')}")
                    new_audio = st.file_uploader("음원 교체", type=["mp3"], key=f"audio_{song.get('id')}")
                    save = st.form_submit_button("수정 저장")
                    if save:
                        ok = update_song(str(song.get("id")), {
                            "title": title,
                            "style_tags": style_tags,
                            "description": description,
                            "lyrics": lyrics,
                            "comments_enabled": comments_enabled,
                            "visibility": visibility,
                            "status": "active",
                        }, new_cover_file=new_cover, new_audio_file=new_audio)
                        if ok:
                            st.success("수정되었습니다.")
                            rerun()
                if st.button("삭제", key=f"delete_{song.get('id')}", type="secondary"):
                    if delete_song(str(song.get("id"))):
                        st.success("삭제 처리되었습니다.")
                        rerun()


def render_playlists_page():
    st.markdown("<div class='busy-section-title'>플레이리스트</div>", unsafe_allow_html=True)
    st.markdown("<div class='busy-card busy-muted'>준비 중</div>", unsafe_allow_html=True)


def render_ai_curation_page():
    st.markdown("<div class='busy-section-title'>AI 큐레이션</div>", unsafe_allow_html=True)
    st.markdown("<div class='busy-card busy-muted'>준비 중</div>", unsafe_allow_html=True)


def render_my_page():
    if not is_logged_in():
        st.markdown("<div class='busy-section-title'>Account</div>", unsafe_allow_html=True)
        if is_login_available():
            if st.button("로그인", use_container_width=True, type="primary"):
                st.login()
        else:
            st.info("Login API unavailable")
        return
    profile = ensure_profile() or {}
    display_name = profile.get("display_name") or profile.get("email") or "내 계정"
    avatar = profile.get("avatar_url") or ""
    st.markdown(f"<div class='busy-section-title'>{html.escape(display_name)}</div>", unsafe_allow_html=True)
    left, right = st.columns([1, 2], gap="large")
    with left:
        if avatar:
            st.image(avatar, width=180)
        if profile.get("email"):
            st.caption(profile.get("email"))
        if st.button("프로필 수정", use_container_width=True):
            st.session_state["busy_nav"] = "Profile"
            rerun()
        if st.button("업로드 관리", use_container_width=True):
            st.session_state["busy_nav"] = "Manage"
            rerun()
        if st.button("새 곡 업로드", use_container_width=True, type="primary"):
            st.session_state["busy_nav"] = "Upload"
            rerun()
        st.divider()
        if st.button("로그아웃", use_container_width=True):
            st.logout()
    with right:
        bio = profile.get("bio") or ""
        if bio:
            st.write(bio)
        links = []
        for label, key in [("Suno", "suno_url"), ("Spotify", "spotify_url"), ("YouTube", "youtube_url"), ("Instagram", "instagram_url"), ("Website", "website_url")]:
            url = profile.get(key)
            if url:
                links.append(f"[{label}]({url})")
        if links:
            st.markdown(" · ".join(links))
        st.markdown("<div class='busy-divider'></div>", unsafe_allow_html=True)
        my_count = len(list_my_songs())
        st.markdown(f"<div class='busy-card'>업로드한 곡 <b>{my_count}</b>개</div>", unsafe_allow_html=True)


def nav_items() -> List[str]:
    return ["Chart", "Playlists", "AI", "My"]


def render_nav_buttons():
    items = ["Chart", "Playlists", "AI"]
    current = st.session_state.get("busy_nav", "Chart")
    labels = {"Chart": "차트", "Playlists": "플레이리스트", "AI": "AI 큐레이션"}
    visible_current = current if current in items else "My" if current in ["My", "Profile", "Upload", "Manage"] else "Chart"

    cols = st.columns([1, 1, 1, 1.15], gap="small")
    for item, col in zip(items, cols[:3]):
        with col:
            button_type = "primary" if item == visible_current else "secondary"
            if st.button(labels.get(item, item), key=f"nav_{item}", type=button_type, use_container_width=True):
                st.session_state["busy_nav"] = item
                rerun()

    with cols[3]:
        if is_logged_in():
            profile = ensure_profile() or {}
            my_label = (profile.get("display_name") or "내 아이디").strip()
            if len(my_label) > 14:
                my_label = my_label[:13] + "…"
            pop_label = f"{my_label} ▾"
            try:
                with st.popover(pop_label, use_container_width=True):
                    if st.button("내 계정", key="my_menu_account", use_container_width=True, type="primary" if visible_current == "My" else "secondary"):
                        st.session_state["busy_nav"] = "My"
                        rerun()
                    if st.button("프로필 수정", key="my_menu_profile", use_container_width=True):
                        st.session_state["busy_nav"] = "Profile"
                        rerun()
                    if st.button("새 곡 업로드", key="my_menu_upload", use_container_width=True):
                        st.session_state["busy_nav"] = "Upload"
                        rerun()
                    if st.button("업로드 관리", key="my_menu_manage", use_container_width=True):
                        st.session_state["busy_nav"] = "Manage"
                        rerun()
                    st.divider()
                    if st.button("로그아웃", key="my_menu_logout", use_container_width=True):
                        st.logout()
            except Exception:
                # Fallback for older Streamlit versions without st.popover
                if st.button(pop_label, key="nav_My", type="primary" if visible_current == "My" else "secondary", use_container_width=True):
                    st.session_state["busy_nav"] = "My"
                    rerun()
        else:
            if st.button("로그인", key="nav_login", type="primary" if visible_current == "My" else "secondary", use_container_width=True):
                st.session_state["busy_nav"] = "My"
                rerun()


def render_nav():
    current = st.session_state.get("busy_nav", "Chart")
    allowed = nav_items() + ["Profile", "Upload", "Manage"]
    if current not in allowed:
        current = "Chart"
        st.session_state["busy_nav"] = current
    return current


def main():
    inject_css()
    render_header()
    if not is_supabase_ready():
        st.error("Server setup required.")
        return
    nav = render_nav()
    if nav == "Chart":
        render_chart()
    elif nav == "Playlists":
        render_playlists_page()
    elif nav == "AI":
        render_ai_curation_page()
    elif nav == "My":
        render_my_page()
    elif nav == "Profile":
        render_profile_page()
    elif nav == "Upload":
        render_upload_page()
    elif nav == "Manage":
        render_manage_page()
    # Keep operational errors out of the public UI.


if __name__ == "__main__":
    main()
