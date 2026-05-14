# Suno Chart

Streamlit + Supabase 기반 Suno 차트 앱입니다.

## 현재 운영 구조

- 앱 표시 데이터: Supabase `app_payloads.latest`
- 곡 마스터: Supabase `suno_songs`
- 곡 수치 히스토리: Supabase `suno_song_history`
- 순위 히스토리: Supabase `suno_rank_history`
- 수동 추가 대기열: Supabase `manual_song_queue`
- 사용자 기능: Google login + Supabase `user_profiles`, `playlists`, `playlist_items`

`data` 브랜치 ZIP 압축/암호화 저장은 더 이상 기본 운영 경로가 아닙니다. 앱에는 Supabase 장애 시 기존 ZIP payload를 읽는 fallback만 남겨두었습니다.

## GitHub Actions

각 업데이트는 별도 workflow로 분리되어 있습니다. 모든 workflow는 `suno-supabase-update` concurrency 그룹을 공유하므로, 서로 같은 테이블을 동시에 덮어쓰는 충돌을 피하기 위해 순차 처리됩니다.

- `Update New Suno Songs`: 00/30분, 신규곡 feed + 수동 queue + payload
- `Update Existing Suno Songs`: 5/20/35/50분, 기존곡 play/like/comment 갱신 + payload
- `Update Comment Quality`: 매시 12분, 댓글 품질 재분석 + payload
- `Update Loudness`: 2시간마다 25분, LUFS 분석 + payload
- `Rebuild App Payload`: 수동 payload 재생성
- `Update Suno Song Stats`: 수동 통합 실행용

필수 GitHub Repository Secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Streamlit Secrets

필수:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY`
- `[auth]` Google OIDC 설정

## Supabase SQL

- `supabase/schema.sql`: 로그인/플레이리스트/앱 사용자 기능 테이블
- `supabase/playlist_rpc.sql`: JS 플레이어의 Cloud Playlist 저장/불러오기 RPC
- `supabase/suno_operational_patch.sql`: Suno raw 테이블 운영 보강 및 `app_payloads` 설정

## Archive 정책

`archive`로 active DB에서 곡을 빼지 않습니다.

- `suno_songs`: 전체 곡 계속 보관
- Top 200: `created_at` 기준 4일 이내만 payload/ranking에서 필터링
- archive 테이블은 legacy/추후 최종 스냅샷 용도로만 선택 사용
