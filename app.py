"""
Suno Chart auth gateway.

사용법:
1. 기존 정상 차트 app.py를 chart_app.py 로 이름 변경
2. 이 파일을 app.py 로 업로드
3. Streamlit secrets에 [auth] Google 설정 입력
4. 로그인 성공 시 chart_app.py를 실행

주의:
- chart_app.py 안의 st.set_page_config는 그대로 둬도 됩니다.
- 이 gateway 파일에서는 st.set_page_config를 호출하지 않습니다.
"""

import os
import runpy
import streamlit as st


CHART_APP_PATH = os.getenv("SUNO_CHART_APP_PATH", "chart_app.py")


def is_logged_in() -> bool:
    try:
        return bool(getattr(st.user, "is_logged_in", False))
    except Exception:
        return False


def user_value(key: str, default: str = "") -> str:
    try:
        value = st.user.get(key, default)
        return "" if value is None else str(value)
    except Exception:
        return default


def render_login_page() -> None:
    st.title("Suno Chart")
    st.subheader("Google login test")

    st.info("Google 로그인에 성공하면 기존 차트 앱으로 이동합니다.")

    try:
        st.button("Log in with Google", on_click=st.login, type="primary")
    except Exception as e:
        st.error("Google 로그인 설정을 읽는 중 오류가 발생했습니다.")
        st.code(str(e))
        st.caption(
            "Streamlit Secrets의 [auth] 설정, Google Client ID/Secret, "
            "redirect_uri를 확인하세요."
        )

    with st.expander("필요한 Streamlit Secrets 예시"):
        st.code("""
DATA_ZIP_PASSWORD = "..."
GITHUB_ACTION_TOKEN = "..."

[auth]
redirect_uri = "https://sunotrending.streamlit.app/oauth2callback"
cookie_secret = "긴_랜덤_문자열"
client_id = "Google_Client_ID.apps.googleusercontent.com"
client_secret = "Google_Client_Secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
""".strip(), language="toml")


def run_chart_app() -> None:
    if not os.path.exists(CHART_APP_PATH):
        st.error(f"{CHART_APP_PATH} 파일을 찾을 수 없습니다.")
        st.write("기존 정상 app.py를 chart_app.py로 이름 변경했는지 확인하세요.")
        st.stop()

    # 로그인 상태를 사이드바에 가볍게 표시한다.
    with st.sidebar:
        st.subheader("Account")
        name = user_value("name")
        email = user_value("email")
        if name:
            st.write(name)
        if email:
            st.caption(email)
        st.button("Log out", on_click=st.logout)

    # 기존 차트 앱 실행.
    # chart_app.py 내부의 st.set_page_config가 여기서 실행된다.
    runpy.run_path(CHART_APP_PATH, run_name="__main__")


if is_logged_in():
    run_chart_app()
else:
    render_login_page()
