# Supabase 중심 운영 전환 패치

이 패치는 기존 `data` 브랜치 ZIP을 운영 DB처럼 쓰던 구조를 줄이고, Supabase를 메인 데이터 저장소로 쓰도록 바꿉니다.

## 반영된 방향

- 앱은 먼저 Supabase `app_payloads` 테이블의 `key='latest'`를 읽습니다.
- Supabase payload가 없거나 실패하면 기존 ZIP payload로 fallback합니다.
- 업데이트 Actions는 더 이상 data 브랜치 ZIP을 수정/push하지 않습니다.
- 업데이트 Actions는 Supabase RAW 테이블을 CSV처럼 읽어 기존 처리 스크립트를 돌린 뒤 다시 Supabase에 저장합니다.
- 4일 지난 곡은 `archive`로 이동/삭제하지 않습니다.
- `Top 200`/랭킹 payload 생성 시점에만 `created_at >= now - 4 days` 조건으로 제외합니다.
- 수동 곡 추가 queue도 Supabase `manual_song_queue`에 먼저 저장합니다. Supabase가 없을 때만 기존 GitHub queue fallback을 사용합니다.

## 필요한 Supabase 테이블

이미 직접 업로드용 SQL로 아래 테이블을 만들고 CSV를 업로드했다면 그대로 사용하면 됩니다.

- `suno_songs`
- `suno_song_history`
- `suno_rank_history`
- `manual_song_queue`
- `app_payloads`
- `suno_song_archive`는 legacy 호환용으로만 남습니다. 앞으로는 필수 역할이 아닙니다.

추가로 Supabase SQL Editor에서 아래 파일을 한 번 실행하세요.

```text
supabase/suno_operational_patch.sql
```

이 SQL은 기존 데이터를 지우지 않고, 필요한 컬럼/인덱스만 보강합니다.

## GitHub Actions Secrets

GitHub 저장소 → Settings → Secrets and variables → Actions → Repository secrets에 아래가 필요합니다.

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

`SUPABASE_URL`은 Repository variables에 있어도 읽도록 workflow를 구성했지만, `SUPABASE_SERVICE_ROLE_KEY`는 반드시 Secret 권장입니다.

## Streamlit Secrets

앱 표시/로그인/플레이리스트에는 기존처럼 아래가 필요합니다.

```toml
SUPABASE_URL = "https://...supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "..."
SUPABASE_ANON_KEY = "..."

[auth]
redirect_uri = "https://sunotrending.streamlit.app/oauth2callback"
cookie_secret = "..."
client_id = "..."
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

## 새 업데이트 스케줄

`.github/workflows/update.yml` 하나가 다음처럼 동작합니다.

- 매시 00분/30분: 신규곡 수집 + 기존곡 업데이트
- 매시 15분/45분: 기존곡 업데이트만

수동 실행도 가능합니다.

```text
Actions → Update Suno Song Stats → Run workflow → mode: full 또는 existing
```

## 주의

첫 실행은 Supabase 테이블 전체를 읽고 다시 쓰므로 시간이 조금 걸릴 수 있습니다.
기존 ZIP/data 브랜치 업데이트 workflow는 이 패치의 `update.yml`로 대체됩니다.
