# GitHub Actions로 CSV → Supabase 마이그레이션하기

로컬에서 Python을 실행하지 않아도 됩니다. GitHub 웹 화면에서 데이터 ZIP을 올리고 Actions 버튼만 누르면 Supabase로 업로드됩니다.

## 1. Supabase 테이블 생성

먼저 Supabase Dashboard → SQL Editor에서 아래 파일 내용을 실행하세요.

```text
supabase/suno_full_schema.sql
```

이미 실행했다면 다시 실행해도 대부분 `if not exists`라 안전합니다.

## 2. GitHub Secrets 확인

GitHub 저장소 → Settings → Secrets and variables → Actions → Repository secrets에 아래 값이 있어야 합니다.

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Streamlit Secrets가 아니라 **GitHub Actions Secrets**입니다.

## 3. 데이터 ZIP 업로드

최신 데이터 ZIP을 GitHub 웹에서 아래 경로에 업로드하세요.

```text
migration_data/sunotrending-data.zip
```

압축을 풀 필요 없습니다. workflow가 알아서 unzip합니다.

ZIP 안 구조는 둘 중 하나면 됩니다.

```text
data/suno_song_db.csv
```

또는

```text
suno_song_db.csv
```

필수/권장 파일:

```text
suno_song_db.csv
suno_song_history.csv
suno_rank_history.csv
suno_song_archive.csv
manual_song_queue.csv
suno_app_payload.json
```

## 4. Actions 실행

GitHub → Actions → `Migrate CSV to Supabase` → Run workflow

처음에는 반드시:

```text
dry_run = true
```

으로 실행하세요. 성공하면 실제 업로드:

```text
dry_run = false
```

로 다시 실행하면 됩니다.

## 5. 업로드 확인

실행이 끝나면 로그에 row count가 표시됩니다. Supabase Table Editor에서도 아래 테이블의 행 수를 확인하세요.

```text
suno_songs
suno_song_history
suno_rank_history
suno_song_archive
manual_song_queue
app_payloads
```

## 주의

- `SUPABASE_SERVICE_ROLE_KEY`는 GitHub 코드에 넣지 말고 GitHub Actions Secrets에만 넣으세요.
- CSV를 Supabase Dashboard에서 직접 import하다가 `22P02`가 뜨는 경우, 이 workflow 방식이 더 안전합니다.
- `suno_app_payload.json`은 CSV import가 아니라 이 workflow가 `app_payloads` 테이블에 JSONB로 넣습니다.
