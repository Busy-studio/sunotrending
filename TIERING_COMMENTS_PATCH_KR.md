# 업데이트 티어링 + 댓글 DB 증분 분석 통합 패치

## 반영 사항

### 1. 업데이트 티어링

`suno_songs`는 전체 곡을 계속 보관합니다. 실제 Suno fetch 대상만 아래 조건으로 줄입니다.

- `hot`: 생성 4일 이내 / created_at 누락 곡
- `playlist`: 4일 초과지만 Cloud Playlist에 포함된 곡
- `warm`: Rain Crew 등 중요 계정의 오래된 곡
- `cold`: 오래됐고 참조되지 않는 곡
- `frozen`: 반복 실패 / 삭제 / 비공개 의심 곡

각 곡에는 아래 운영 컬럼이 추가됩니다.

```text
status
update_tier
next_check_at
fetch_fail_count
last_fetch_error
last_change_at
playlist_ref_count
comments_fetch_needed
last_comment_fetch_at
```

### 2. Archive 이동 제거

4일 지난 곡도 `suno_songs`에 계속 남습니다. Top 200 후보에서만 제외됩니다.

### 3. History 누적 완화

기본값으로 최근 7일은 고해상도 기록을 유지하고, 7일 초과 기록은 곡별/일별 마지막 스냅샷만 유지합니다.

```text
COMPACT_HISTORY=1
HISTORY_HIGH_RES_DAYS=7
```

### 4. 댓글 원문 DB 저장

댓글 원문은 `suno_comments`에 저장됩니다.

```text
comment_id
song_id
content
user_handle
num_likes
created_at
quality_label
quality_weight
analyzed_at
```

### 5. 신규 댓글만 분석

기존 댓글을 매번 다시 분석하지 않습니다.

- `comment_count`가 증가한 곡만 댓글 API 호출 후보가 됩니다.
- 새 `comment_id`만 `suno_comments`에 저장합니다.
- `analyzed_at is null` 댓글만 분류합니다.
- 저장된 댓글의 `quality_label/quality_weight`를 기준으로 곡별 요약값을 갱신합니다.

## 적용 순서

1. ZIP을 main 브랜치에 덮어쓰기
2. Supabase SQL Editor에서 실행:

```text
supabase/update_tiering_comments_patch.sql
```

3. GitHub Actions에서 수동 테스트:

```text
Update Suno Song Stats → Run workflow → mode: payload
Update Suno Song Stats → Run workflow → mode: existing
Update Comment Quality → Run workflow
```

또는 통합 실행:

```text
Update Suno Song Stats → mode: full
```

## GitHub Secrets

필수:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

## 주요 환경변수

```text
UPDATE_TIERING_ENABLED=1
COMMENT_DB_ENABLED=1
COMPACT_HISTORY=1
HISTORY_HIGH_RES_DAYS=7
MAX_UPDATE_ROWS=1200
```
