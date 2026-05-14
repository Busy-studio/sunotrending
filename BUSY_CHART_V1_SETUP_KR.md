# Busy Chart v1.0 설정 안내

이번 버전은 기존 Suno 자동 수집 구조를 리셋하고, **사용자 업로드 음원 기반 차트**로 동작합니다.

## 1. Supabase SQL 실행

Supabase → SQL Editor에서 아래 파일 전체를 실행하세요.

```text
supabase/busy_chart_v1_schema.sql
```

생성되는 주요 테이블:

```text
bc_profiles
bc_songs
bc_song_likes
bc_play_events
bc_comments
bc_comment_likes
```

생성되는 Storage bucket:

```text
busy-audio
busy-cover
busy-avatar
```

SQL에서 bucket 생성이 실패하면 Supabase Storage 화면에서 같은 이름으로 직접 만들고 public bucket으로 설정하세요.

## 2. Streamlit Secrets

기존 Google 로그인 설정은 유지하고, 아래 값을 확인하세요.

```toml
SUPABASE_URL = "https://프로젝트.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "service_role_key"
SUPABASE_ANON_KEY = "anon_or_publishable_key"

[auth]
redirect_uri = "https://앱주소/oauth2callback"
cookie_secret = "..."
client_id = "..."
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

`SUPABASE_ANON_KEY`는 브라우저에서 30% 이상 재생 시 `bc_record_play` RPC를 호출하기 위해 필요합니다.

## 3. 사용 방식

비로그인 사용자:

```text
차트 보기
음원 재생/일시정지
좋아요 클릭 가능
댓글 작성/업로드 불가
```

로그인 사용자:

```text
사용자 정보 페이지: 닉네임, 아바타 이미지 업로드
업로드 페이지: 제목, 커버 이미지, 장르/태그, 가사, MP3 업로드, 댓글 허용 설정
업로드곡 관리 페이지: 수정, 삭제, 음원/커버 교체
댓글 작성 가능
```

## 4. 업로드 제한

프로토타입 비용 관리를 위해 기본 제한은 다음과 같습니다.

```text
음원: MP3만 허용, 최대 25MB
커버: JPG/JPEG/PNG/WEBP, 최대 6MB
아바타: JPG/JPEG/PNG/WEBP, 최대 4MB
```

## 5. 재생 카운트

브라우저 오디오 플레이어에서 곡 길이의 30% 이상 재생되면 `bc_play_events`에 1회 기록됩니다.
같은 브라우저 세션에서 같은 곡은 중복 카운트되지 않도록 `unique(song_id, session_id)`를 사용합니다.

## 6. GitHub Actions

Busy Chart v1.0은 더 이상 Suno 데이터 자동 수집 Actions를 사용하지 않습니다. 기존 workflow는 `.github/workflows_disabled`에 참고용으로 이동했습니다.
