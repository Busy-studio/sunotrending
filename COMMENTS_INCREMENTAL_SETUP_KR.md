# 댓글 DB 저장 + 신규 댓글 증분 분석

이번 패치는 댓글 원문을 `public.suno_comments`에 저장하고, 이미 분석한 댓글은 다시 분석하지 않습니다.

## 핵심 흐름

1. 곡 업데이트에서 `comment_count`가 증가하면 `comments_fetch_needed=1`로 표시됩니다.
2. 댓글 품질 workflow는 Top 200 후보곡을 기준으로 확인합니다.
3. `suno_comments`에 이미 저장된 댓글 수가 현재 `comment_count`보다 적은 곡만 댓글 API를 호출합니다.
4. 새 `comment_id`만 `suno_comments`에 insert/upsert합니다.
5. 분석은 `analyzed_at is null` 댓글만 수행합니다.
6. `suno_songs`의 `adjusted_comment_count`, `comment_quality_ratio`, `meaningful_count` 등은 저장된 댓글 라벨/가중치 기준으로 갱신합니다.

## 먼저 실행할 SQL

Supabase SQL Editor에서 실행:

```text
supabase/update_tiering_comments_patch.sql
```

## 운영 변수

GitHub Actions workflow에 기본값이 들어 있습니다.

```text
COMMENT_DB_ENABLED=1
COMMENT_ANALYZE_TOP_N=200
COMMENT_MAX_PAGES=3
COMMENT_MAX_ITEMS_PER_SONG=120
UPDATE_TIERING_ENABLED=1
COMPACT_HISTORY=1
HISTORY_HIGH_RES_DAYS=7
```

## 전체 재분석이 필요한 경우

댓글 분류 기준을 크게 바꾼 경우에는 `suno_comments`의 `analyzed_at`, `quality_label`, `quality_weight`를 초기화한 뒤 댓글 workflow를 돌리면 됩니다.

```sql
update public.suno_comments
set analyzed_at = null,
    quality_label = null,
    quality_weight = null,
    is_meaningful = null,
    is_generic = null,
    is_mention_only = null,
    is_emoji_only = null;
```
