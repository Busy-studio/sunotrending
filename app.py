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
          --busy-bg:#fbf8ff;
          --busy-card:#ffffff;
          --busy-line:#eadff7;
          --busy-text:#2d2540;
          --busy-muted:#7f7196;
          --busy-lavender:#d9ccff;
          --busy-mint:#c9f1e7;
          --busy-peach:#ffd9c8;
          --busy-sky:#cfe9ff;
          --busy-accent:#8b6eea;
        }
        html, body, [data-testid="stAppViewContainer"] {
          background:
            radial-gradient(circle at top left, rgba(217,204,255,.48), transparent 34%),
            radial-gradient(circle at top right, rgba(201,241,231,.55), transparent 32%),
            linear-gradient(180deg, #fffbfe 0%, #f8fbff 100%) !important;
          color:var(--busy-text);
        }
        .block-container {padding-top: 1.05rem; padding-bottom: 3rem; max-width: 1440px;}
        .busy-topbar {
          display:flex; align-items:center; justify-content:space-between; gap:16px;
          border:1px solid rgba(234,223,247,.95); border-radius:20px; padding:12px 14px;
          background:rgba(255,255,255,.78); backdrop-filter:blur(16px);
          box-shadow:0 14px 40px rgba(93,75,137,.08); margin-bottom:14px;
        }
        .busy-brand {display:flex; align-items:center; gap:10px;}
        .busy-logo {width:38px; height:38px; border-radius:14px; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#b8a7ff,#9de8d7); color:#2d2540; font-weight:1000; box-shadow:0 8px 20px rgba(139,110,234,.18);}
        .busy-brand-title {font-size:22px; font-weight:1000; letter-spacing:-.04em; line-height:1; color:#2d2540;}
        .busy-brand-sub {font-size:12px; color:var(--busy-muted); margin-top:4px;}
        .busy-status {font-size:12px; color:var(--busy-muted); text-align:right;}
        .busy-hero {border:1px solid rgba(234,223,247,.95); border-radius:26px; padding:24px; background:linear-gradient(135deg,#f3edff 0%,#e9fbf6 50%,#fff1ea 100%); color:#2d2540; margin:14px 0 18px; box-shadow:0 18px 50px rgba(93,75,137,.08);}
        .busy-hero-title {font-size:30px; font-weight:1000; letter-spacing:-.05em; line-height:1;}
        .busy-hero-sub {font-size:13px; color:#766a8f; margin-top:8px;}
        .busy-user-chip {display:flex; align-items:center; justify-content:flex-end; gap:8px; font-size:13px; color:#2d2540; font-weight:800;}
        .busy-avatar-sm {width:28px; height:28px; border-radius:999px; object-fit:cover; background:#efe9fb;}
        .busy-section-title {font-size:22px; font-weight:950; letter-spacing:-.03em; margin:14px 0 10px; color:#2d2540;}
        .busy-page-subtitle {font-size:13px; color:var(--busy-muted); margin-top:-5px; margin-bottom:12px;}
        .busy-card {border:1px solid rgba(234,223,247,.95); border-radius:20px; padding:15px; background:rgba(255,255,255,.82); height:100%; box-shadow:0 8px 24px rgba(93,75,137,.055);}
        .busy-song-grid {display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:14px;}
        .busy-song-card {border:1px solid rgba(234,223,247,.95); border-radius:22px; padding:12px; background:rgba(255,255,255,.86); box-shadow:0 10px 26px rgba(93,75,137,.07);}
        .busy-cover-img {width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:17px; background:#f5f0ff; display:block;}
        .busy-song-title {font-weight:900; font-size:15px; margin-top:9px; line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#2d2540;}
        .busy-song-meta {font-size:12px; color:var(--busy-muted); line-height:1.35; margin-top:3px; min-height:32px;}
        .busy-stats {font-size:12px; color:#55496e; display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;}
        .busy-pill {display:inline-flex; align-items:center; border:1px solid #eadff7; border-radius:999px; padding:3px 8px; background:#fbf8ff;}
        .busy-muted {color:var(--busy-muted); font-size:12px;}
        .busy-divider {height:1px; background:#eadff7; margin:16px 0;}

        /* Website-like menu buttons */
        div[data-testid="stHorizontalBlock"] button[kind="secondary"],
        div[data-testid="stHorizontalBlock"] button[kind="primary"] {
          border-radius:12px !important;
          min-height:38px;
          box-shadow:none !important;
          border:1px solid #eadff7 !important;
        }
        div[data-testid="stHorizontalBlock"] button[kind="primary"] {
          background:linear-gradient(135deg,#d9ccff,#c9f1e7) !important;
          color:#2d2540 !important;
        }
        div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
          background:rgba(255,255,255,.72) !important;
          color:#594d72 !important;
        }
        button {font-weight:750 !important;}

        @media (max-width: 900px) {
          .block-container {padding-left:.75rem; padding-right:.75rem;}
          .busy-topbar {display:block;}
          .busy-status {text-align:left; margin-top:10px;}
          .busy-brand-title {font-size:20px;}
          .busy-song-grid {grid-template-columns: repeat(2, minmax(0, 1fr)); gap:10px;}
        }
        @media (max-width: 520px) {
          .busy-song-grid {grid-template-columns:1fr;}
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


def render_song_card(song: Dict, rank: int, liked: bool):
    song_id = str(song.get("id"))
    cover = song.get("cover_url") or ""
    title = song.get("title") or "Untitled"
    artist = song_artist(song)
    tags = song.get("style_tags") or ""
    st.markdown(
        f"""
        <div class="busy-song-card">
          <img class="busy-cover-img" src="{html.escape(cover)}" onerror="this.style.opacity=.15">
          <div class="busy-song-title">#{rank} {html.escape(title)}</div>
          <div class="busy-song-meta">{html.escape(artist)}<br>{html.escape(tags[:90])}</div>
          <div class="busy-stats">
            <span class="busy-pill">▶ {int(song.get('play_count') or 0)}</span>
            <span class="busy-pill">♥ {int(song.get('like_count') or 0)}</span>
            <span class="busy-pill">💬 {int(song.get('comment_count') or 0)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    b1, b2 = st.columns(2)
    with b1:
        if st.button("♥ 좋아요" if not liked else "♥ 취소", key=f"like_{song_id}", use_container_width=True):
            toggle_song_like(song_id)
            rerun()
    with b2:
        if st.button("상세", key=f"detail_{song_id}", use_container_width=True):
            st.session_state["selected_song_id"] = song_id
            rerun()


def render_chart():
    st.markdown("""
        <div class='busy-hero'>
          <div class='busy-hero-title'>Busy Chart</div>
          <div class='busy-hero-sub'>Fresh tracks, playlists, and AI-powered curation.</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("<div class='busy-section-title'>Chart</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        order_label = st.selectbox("정렬", ["Trending", "New", "Most Liked", "Most Played"], label_visibility="collapsed")
    with c2:
        limit = st.selectbox("표시", [50, 100, 200, 300], index=0, label_visibility="collapsed")
    order_map = {"Trending": "score", "New": "new", "Most Liked": "liked", "Most Played": "played"}
    songs = list_songs(limit=limit, order=order_map[order_label])
    if not songs:
        st.markdown("<div class='busy-card busy-muted'>No tracks yet.</div>", unsafe_allow_html=True)
        return
    liked = liked_song_ids([str(s.get("id")) for s in songs])
    cols = st.columns(4)
    for idx, song in enumerate(songs, start=1):
        with cols[(idx - 1) % 4]:
            render_song_card(song, idx, str(song.get("id")) in liked)
    selected = st.session_state.get("selected_song_id")
    if selected:
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
            st.markdown(f"**Style Tags**: {song.get('style_tags')}")
        with st.expander("Lyrics", expanded=False):
            st.text(song.get("lyrics") or "")
    render_comments(song)


def render_comments(song: Dict):
    song_id = str(song.get("id"))
    st.markdown("<div class='busy-section-title'>Comments</div>", unsafe_allow_html=True)
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
    st.markdown("<div class='busy-section-title'>Profile</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    profile = ensure_profile() or {}
    left, right = st.columns([1, 2.2], gap="large")
    with left:
        if profile.get("avatar_url"):
            st.image(profile.get("avatar_url"), width=180)
        else:
            st.markdown("<div class='busy-card busy-muted'>No avatar</div>", unsafe_allow_html=True)
        if profile.get("email"):
            st.caption(f"Email: {profile.get('email')}")
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
    st.markdown("<div class='busy-section-title'>Upload</div>", unsafe_allow_html=True)
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
    st.markdown("<div class='busy-section-title'>My Uploads</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    songs = list_my_songs()
    if st.button("+ New Upload"):
        st.session_state["busy_nav"] = "Upload"
        rerun()
    if not songs:
        st.markdown("<div class='busy-card busy-muted'>No uploads yet.</div>", unsafe_allow_html=True)
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
    st.markdown("<div class='busy-section-title'>Playlists</div>", unsafe_allow_html=True)
    st.markdown("<div class='busy-card busy-muted'>플레이리스트 기능은 다음 단계에서 연결됩니다.</div>", unsafe_allow_html=True)


def render_ai_curation_page():
    st.markdown("<div class='busy-section-title'>AI Curation</div>", unsafe_allow_html=True)
    st.markdown("<div class='busy-card busy-muted'>업로드된 곡을 바탕으로 AI 플레이리스트를 만드는 기능을 준비 중입니다.</div>", unsafe_allow_html=True)


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
    items = nav_items()
    profile = ensure_profile() if is_logged_in() else {}
    if is_logged_in():
        my_label = (profile or {}).get("display_name") or "내 아이디"
    else:
        my_label = "로그인"
    labels = {"Chart": "차트", "Playlists": "플레이리스트", "AI": "AI 큐레이션", "My": my_label}
    current = st.session_state.get("busy_nav", "Chart")
    visible_current = current if current in items else "My" if current in ["Profile", "Upload", "Manage"] else "Chart"
    cols = st.columns(len(items), gap="small")
    for item, col in zip(items, cols):
        with col:
            button_type = "primary" if item == visible_current else "secondary"
            if st.button(labels.get(item, item), key=f"nav_{item}", type=button_type, use_container_width=True):
                st.session_state["busy_nav"] = item
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
