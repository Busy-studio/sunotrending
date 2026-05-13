# Parallel GitHub Actions update structure

이 패치는 신규곡 수집과 기존곡 수치 갱신을 분리합니다.

## Schedule

- `0,30 * * * *`: `full_parallel`
  - 신규곡 수집
  - 기존곡 4-shard 병렬 상세 갱신
  - 최종 병합/랭킹/payload/encrypt/push

- `15,45 * * * *`: `existing_parallel`
  - 신규곡 수집 없이 기존곡 4-shard 병렬 상세 갱신
  - 최종 병합/랭킹/payload/encrypt/push

## Why this avoids conflicts

각 shard job은 DB ZIP을 직접 push하지 않습니다.

1. `prepare-data`가 data 브랜치 최신 ZIP을 내려받고 복호화합니다.
2. `fetch-existing-shards` 4개가 같은 대상 목록을 deterministic하게 나눠 fetch하고, partial CSV만 artifact로 올립니다.
3. `merge-and-publish` 하나만 partial CSV들을 합치고 data 브랜치에 push합니다.

즉 fetch는 병렬, write/push는 단일 job입니다.

## Main knobs

`.github/workflows/update.yml` 상단 env에서 조정합니다.

```yaml
SHARD_COUNT: "4"
SHARD_UPDATE_ROWS_TOTAL: "1200"
REQUEST_SLEEP_SECONDS: "0.8"
```

- `SHARD_UPDATE_ROWS_TOTAL=1200`, `SHARD_COUNT=4`이면 각 shard가 대략 300곡씩 맡습니다.
- GitHub Actions 소요시간이 길면 `SHARD_UPDATE_ROWS_TOTAL`을 800~1000으로 줄이세요.
- Suno 쪽 요청 실패가 늘면 `REQUEST_SLEEP_SECONDS`를 1.0~1.5로 올리세요.

## Manual run modes

Actions → `Update Suno Song Stats` → Run workflow

- `full_parallel`: 신규곡 + 기존곡 병렬 갱신
- `existing_parallel`: 기존곡만 병렬 갱신
- `new_only`: 신규곡만 수집 후 payload 생성
- `manual_add`: 수동 URL 추가

## Added scripts

- `scripts/update_new_songs_only.py`
- `scripts/update_existing_song_shard.py`
- `scripts/merge_shard_updates.py`
