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
        #MainMenu {visibility:hidden;}
        footer {visibility:hidden;}
        header[data-testid="stHeader"] {background: rgba(255,255,255,0.85); backdrop-filter: blur(10px);}
        .block-container {padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1440px;}
        .busy-hero {border:1px solid #e5e7eb; border-radius:24px; padding:22px 22px; background:linear-gradient(135deg,#fff,#f8fafc); margin-bottom:14px;}
        .busy-title {font-size:34px; font-weight:1000; letter-spacing:-0.04em; margin:0;}
        .busy-subtitle {font-size:14px; color:#6b7280; margin-top:6px;}
        .busy-card {border:1px solid #e5e7eb; border-radius:20px; padding:14px; background:#fff; height:100%;}
        .busy-song-grid {display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:14px;}
        .busy-song-card {border:1px solid #e5e7eb; border-radius:18px; padding:12px; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.03);}
        .busy-cover-img {width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:14px; background:#f3f4f6; display:block;}
        .busy-song-title {font-weight:900; font-size:15px; margin-top:9px; line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        .busy-song-meta {font-size:12px; color:#6b7280; line-height:1.35; margin-top:3px; min-height:32px;}
        .busy-stats {font-size:12px; color:#374151; display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;}
        .busy-pill {display:inline-flex; align-items:center; border:1px solid #e5e7eb; border-radius:999px; padding:3px 8px; background:#f9fafb;}
        .busy-muted {color:#6b7280; font-size:12px;}
        .busy-section-title {font-size:21px; font-weight:950; letter-spacing:-.02em; margin:12px 0 8px;}
        .busy-divider {height:1px; background:#e5e7eb; margin:16px 0;}
        @media (max-width: 900px) {
          .block-container {padding-left: .75rem; padding-right: .75rem;}
          .busy-title {font-size:26px;}
          .busy-song-grid {grid-template-columns: repeat(2, minmax(0, 1fr)); gap:10px;}
        }
        @media (max-width: 520px) {
          .busy-song-grid {grid-template-columns: 1fr;}
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
    st.markdown(
        f"""
        <div class="busy-hero">
          <div class="busy-title">{APP_TITLE}</div>
          <div class="busy-subtitle">사용자 업로드 음원 기반 차트 · MP3 + 앨범 이미지 · 앱 내부 재생수/좋아요/댓글 반영</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, mid, right = st.columns([1.4, 1.4, 1.0], gap="small")
    with left:
        if is_logged_in():
            profile = ensure_profile() or {}
            st.caption(f"로그인됨: {profile.get('display_name') or profile.get('email') or 'Busy User'}")
        else:
            st.caption("비로그인 상태: 차트 감상, 재생/일시정지, 좋아요 가능 · 업로드/댓글은 로그인 필요")
    with mid:
        st.caption("서버 연결됨" if is_supabase_ready() else "서버 설정 필요: SUPABASE_URL / SERVICE_ROLE_KEY")
    with right:
        if not is_login_available():
            st.caption("Streamlit 로그인 API 확인 필요")
        elif is_logged_in():
            if st.button("Logout", use_container_width=True):
                st.logout()
        else:
            if st.button("Login with Google", use_container_width=True):
                st.login()


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
    st.markdown("<div class='busy-section-title'>Chart</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        order_label = st.selectbox("정렬", ["Trending", "New", "Most Liked", "Most Played"], label_visibility="collapsed")
    with c2:
        limit = st.selectbox("표시", [50, 100, 200, 300], index=0, label_visibility="collapsed")
    order_map = {"Trending": "score", "New": "new", "Most Liked": "liked", "Most Played": "played"}
    songs = list_songs(limit=limit, order=order_map[order_label])
    if not songs:
        st.info("아직 업로드된 곡이 없습니다. 로그인 후 업로드 페이지에서 첫 곡을 등록해보세요.")
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
    st.markdown("<div class='busy-section-title'>사용자 정보</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    profile = ensure_profile() or {}
    left, right = st.columns([1, 2])
    with left:
        if profile.get("avatar_url"):
            st.image(profile.get("avatar_url"), width=160)
    with right:
        with st.form("profile_form"):
            display_name = st.text_input("닉네임", value=profile.get("display_name") or "")
            avatar = st.file_uploader("아바타 이미지", type=["jpg", "jpeg", "png", "webp"])
            submitted = st.form_submit_button("저장")
            if submitted:
                if update_profile(display_name, avatar):
                    st.success("프로필이 저장되었습니다.")
                    rerun()


def render_upload_page():
    st.markdown("<div class='busy-section-title'>업로드</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("업로드는 로그인 후 사용할 수 있습니다.")
        return
    ensure_profile()
    st.caption(f"현재 프로토타입은 MP3 최대 {MAX_AUDIO_MB}MB, 앨범 이미지는 JPG/PNG/WEBP 최대 {MAX_COVER_MB}MB만 지원합니다.")
    with st.form("upload_form"):
        title = st.text_input("노래 제목 *", max_chars=160)
        style_tags = st.text_input("스타일태그 / 장르", placeholder="예: hard psy, vocal chop, synth-pop", max_chars=300)
        description = st.text_area("곡 소개", max_chars=2000)
        lyrics = st.text_area("가사", height=180, max_chars=20000)
        audio = st.file_uploader("음원 파일 *", type=["mp3"])
        cover = st.file_uploader("앨범 이미지 *", type=["jpg", "jpeg", "png", "webp"])
        comments_enabled = st.checkbox("댓글 허용", value=True)
        rights = st.checkbox("나는 이 음원을 업로드하고 공개/공유/재생할 권리를 보유하고 있거나 필요한 허가를 받았으며, 제3자의 권리 및 외부 플랫폼 약관을 침해하지 않음을 확인합니다.")
        submitted = st.form_submit_button("곡 등록")
        if submitted:
            if not rights:
                st.error("권리 확인 동의가 필요합니다.")
            elif has_bad_words(title + style_tags + description):
                st.error("입력 내용에 제한된 표현이 포함되어 있습니다.")
            else:
                song_id = create_song(title, style_tags, lyrics, audio, cover, comments_enabled, description)
                if song_id:
                    st.success("곡이 등록되었습니다. 차트에 즉시 반영됩니다.")
                    st.session_state["selected_song_id"] = song_id


def render_manage_page():
    st.markdown("<div class='busy-section-title'>업로드곡 관리</div>", unsafe_allow_html=True)
    if not is_logged_in():
        st.info("로그인이 필요합니다.")
        return
    songs = list_my_songs()
    if st.button("+ 새 곡 업로드 페이지로 이동"):
        st.session_state["busy_nav"] = "Upload"
        rerun()
    if not songs:
        st.info("아직 업로드한 곡이 없습니다.")
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


def render_nav():
    public_tabs = ["Chart"]
    private_tabs = ["Profile", "Upload", "Manage"] if is_logged_in() else []
    tabs = public_tabs + private_tabs
    current = st.session_state.get("busy_nav", "Chart")
    if current not in tabs:
        current = "Chart"
    selected = st.radio("Navigation", tabs, index=tabs.index(current), horizontal=True, label_visibility="collapsed")
    st.session_state["busy_nav"] = selected
    return selected


def main():
    inject_css()
    render_header()
    if not is_supabase_ready():
        st.error("Supabase 연결이 필요합니다. Streamlit Secrets에 SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY를 설정하고, supabase/busy_chart_v1_schema.sql을 실행하세요.")
        return
    nav = render_nav()
    if nav == "Chart":
        render_chart()
    elif nav == "Profile":
        render_profile_page()
    elif nav == "Upload":
        render_upload_page()
    elif nav == "Manage":
        render_manage_page()
    err = st.session_state.get("busy_last_error")
    if err:
        with st.expander("최근 서버 메시지", expanded=False):
            st.code(str(err)[:2000])


if __name__ == "__main__":
    main()
