# Optimization Summary

## UI/mobile

- 수동 곡 추가 폼을 기본 접힘(expander)으로 변경해 모바일에서 차트 영역을 밀어내지 않도록 조정했습니다.
- 모바일 폭에서는 왼쪽 풀 플레이어를 숨기고 차트 우선 표시로 전환했습니다.
- 비로그인/모바일에서도 앨범 이미지 클릭으로 단일곡 재생/일시정지는 유지됩니다.
- 모바일 차트는 가로 스크롤 테이블로 유지해 컬럼이 잘리지 않도록 했습니다.

## Supabase update workflows

기존 단일 스케줄 workflow를 기능별 workflow로 분리했습니다.

- `update-new-songs.yml`: 00/30분, 신규곡 + 수동 queue + payload
- `update-existing-songs.yml`: 5/20/35/50분, 기존곡 수치 갱신 + payload
- `update-comment-quality.yml`: 매시 12분, 댓글 품질 + payload
- `update-loudness.yml`: 2시간마다 25분, LUFS + payload
- `rebuild-app-payload.yml`: 수동 payload 재생성
- `update.yml`: 수동 통합 실행용

각 workflow는 별도 실행되지만 같은 `suno-supabase-update` concurrency 그룹을 사용해 Supabase raw table 전체 replace 중 충돌을 피합니다.

## Archive policy

- 4일 지난 곡을 `suno_songs`에서 제거하지 않습니다.
- Top 200/ranking payload에서만 4일 기준으로 제외합니다.
- `suno_song_archive`는 기본 pull/push 대상에서 제외되어 빈 파일 문제로 Actions가 실패하지 않습니다.

## Removed legacy files

- data-branch migration workflow/files
- previous phase docs
- parallel shard artifact scripts
- local encrypted zip output files from main branch
- Python `__pycache__` files

ZIP fallback 관련 최소 파일(`data_loader.py`, `secure_csv.py`, `decrypt_data.py`)은 앱 안정성을 위해 남겨두었습니다.
