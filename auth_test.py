import streamlit as st

st.set_page_config(page_title="Suno Chart Auth Test", layout="centered")

st.title("Suno Chart Auth Test")
st.caption("Google OAuth / Streamlit st.login() 단독 테스트용 파일")

st.divider()

try:
    is_logged_in = bool(getattr(st.user, "is_logged_in", False))
except Exception as e:
    is_logged_in = False
    st.error("st.user 확인 중 오류가 발생했습니다.")
    st.exception(e)

if is_logged_in:
    st.success("로그인 성공")

    st.subheader("User info")
    try:
        st.write("Name:", st.user.get("name", ""))
        st.write("Email:", st.user.get("email", ""))
        st.write("Picture:", st.user.get("picture", ""))
        st.json(dict(st.user))
    except Exception as e:
        st.warning("사용자 정보를 표시하는 중 오류가 발생했습니다.")
        st.exception(e)

    if st.button("Log out"):
        st.logout()
else:
    st.info("아직 로그인하지 않았습니다.")
    st.write("아래 버튼을 누르면 Google 로그인 화면으로 이동해야 합니다.")

    if st.button("Log in with Google"):
        st.login()

st.divider()

st.subheader("Secrets checklist")
st.write("Streamlit Secrets에 아래 형식으로 실제 값을 넣었는지 확인하세요.")

st.code('''DATA_ZIP_PASSWORD = "기존_zip_비밀번호"
GITHUB_ACTION_TOKEN = "github_pat_..."
GITHUB_REPO_OWNER = "Busy-studio"
GITHUB_REPO_NAME = "sunotrending"

[auth]
redirect_uri = "https://sunotrending.streamlit.app/oauth2callback"
cookie_secret = "직접_생성한_긴_랜덤문자열"
client_id = "Google_Client_ID.apps.googleusercontent.com"
client_secret = "Google_Client_Secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
''', language="toml")

st.caption("주의: Google Cloud Console의 Authorized redirect URI도 위 redirect_uri와 완전히 같아야 합니다.")
