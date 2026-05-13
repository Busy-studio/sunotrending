# Suno Chart Supabase 1차 적용 안내

이 버전은 기존 Suno Chart 구조를 유지하면서 Supabase를 사용자 데이터 저장용으로 붙인 1차 적용판입니다.

## 이번 ZIP에 들어간 변경사항

- `app_modules/supabase_store.py` 추가
  - Supabase 연결
  - Google 로그인 사용자 프로필 저장
  - 플레이리스트/좋아요/재생 로그용 함수 준비
- `supabase/schema.sql` 추가
  - Supabase SQL Editor에서 한 번 실행할 테이블 생성 SQL
- `app.py` 수정
  - 상단 로그인/로그아웃 영역 추가
  - 로그인 성공 시 `user_profiles`에 사용자 저장
  - Supabase 연결 상태 표시
  - 내 플레이리스트 목록 표시 준비
- `requirements.txt` 수정
  - `supabase` 패키지 추가

## 1. Supabase SQL 실행

Supabase Dashboard → SQL Editor → New query에서 아래 파일 내용을 실행하세요.

```text
supabase/schema.sql
```

실행 후 Table Editor에 아래 테이블이 생기면 정상입니다.

- `user_profiles`
- `playlists`
- `playlist_items`
- `app_likes`
- `app_play_events`
- `app_song_stats`

## 2. Streamlit Cloud Secrets 설정

Streamlit Cloud → 해당 앱 → Settings → Secrets에 아래 형식으로 추가하세요.

```toml
SUPABASE_URL = "https://YOUR_PROJECT_ID.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "YOUR_SUPABASE_SERVICE_ROLE_KEY"

[auth]
redirect_uri = "https://sunotrending.streamlit.app/oauth2callback"
cookie_secret = "아무도_모르는_긴_랜덤_문자열_32자_이상"
client_id = "GOOGLE_CLIENT_ID"
client_secret = "GOOGLE_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

주의:

- `SUPABASE_SERVICE_ROLE_KEY`는 절대 GitHub 코드에 넣지 마세요.
- 위 값은 반드시 Streamlit Secrets에만 넣으세요.
- 로컬 테스트를 한다면 `.streamlit/secrets.toml`에 같은 형식으로 넣으면 됩니다.

## 3. Google OAuth Redirect URI 확인

Google Cloud Console의 OAuth Client 설정에서 Authorized redirect URI에 아래 주소가 있어야 합니다.

```text
https://sunotrending.streamlit.app/oauth2callback
```

로컬에서 테스트할 경우 아래도 추가하세요.

```text
http://localhost:8501/oauth2callback
```

## 4. GitHub에 업로드

이 ZIP의 내용을 기존 GitHub 저장소에 덮어쓴 뒤 commit/push 하세요.

예시:

```bash
git add app.py app_modules/supabase_store.py requirements.txt SUPABASE_SETUP.md supabase/schema.sql
git commit -m "Add Supabase user profile integration"
git push
```

Streamlit Cloud가 자동 재배포되면 앱 상단에 로그인 영역이 보입니다.

## 5. 정상 작동 확인

1. 앱 접속
2. `Login with Google` 클릭
3. 구글 로그인 완료
4. 앱 상단에 이메일 표시 확인
5. Supabase Table Editor → `user_profiles` 확인
6. 본인 이메일과 user_id가 들어갔으면 1차 성공

## 현재 단계에서 아직 안 된 것

이번 1차 버전은 안전한 기반 작업입니다. 아래 기능은 함수와 DB 구조는 준비되어 있지만, 현재 HTML/JS 플레이어와 완전히 연결되지는 않았습니다.

- 현재 재생목록을 Supabase에 저장
- HTML 플레이어 내부 좋아요 버튼
- 30초 이상 재생 시 앱 재생수 카운트
- 앱 좋아요/재생수를 랭킹 점수에 합산

이유는 현재 플레이어가 `components.html()` 내부 JS로 동작하기 때문에, JS 이벤트를 Python/Supabase로 안전하게 보내는 연결 작업이 추가로 필요합니다.

추천 다음 단계:

1. 로그인 + `user_profiles` 저장 확인
2. 내 플레이리스트 저장 UI 연결
3. 앱 좋아요 버튼 연결
4. 재생 이벤트 카운트 연결
5. 공식 Suno 지표 + 앱 내부 지표 보조 반영
