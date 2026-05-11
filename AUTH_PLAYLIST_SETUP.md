# Suno Chart v1.05.3 Auth Stable 설정

이 버전은 v1.04.3의 차트 렌더링 구조를 유지하면서 Google 로그인, 로그인 사용자 수동 곡 추가, 개인 플레이리스트 저장 기반을 추가합니다.

## Streamlit Secrets 예시

```toml
DATA_ZIP_PASSWORD = "기존 ZIP 비밀번호"
GITHUB_ACTION_TOKEN = "github_pat_..."

GITHUB_REPO_OWNER = "Busy-studio"
GITHUB_REPO_NAME = "sunotrending"
APP_PUBLIC_BASE_URL = "https://sunotrending.streamlit.app"

[auth]
redirect_uri = "https://sunotrending.streamlit.app/oauth2callback"
cookie_secret = "직접 생성한 긴 랜덤 문자열"

[auth.google]
client_id = "Google Cloud에서 받은 Client ID"
client_secret = "Google Cloud에서 받은 Client Secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

## Google Cloud OAuth

- Application type: Web application
- Authorized redirect URI: `https://sunotrending.streamlit.app/oauth2callback`
- Authorized JavaScript origin: `https://sunotrending.streamlit.app`

## cookie_secret 생성

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 기능

- 비로그인: 차트 보기/재생 가능
- 로그인: 수동 곡 추가 가능
- 로그인: 개인 플레이리스트 JSON 저장 가능
- 공개 플레이리스트 확장을 위해 `visibility = private/public` 필드 포함
