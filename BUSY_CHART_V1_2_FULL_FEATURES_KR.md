# Busy Chart v1.0.2

사용자 업로드곡 기반으로 기존 차트 앱 기능을 다시 붙인 버전입니다.

## 반영
- 기존 카드형 차트 구조 복원
- 30% 이상 재생 시 재생수 카운트
- 좋아요/댓글/댓글 좋아요
- 상세정보/가사/업로드 관리
- 프로필 링크/아바타
- 플레이리스트 생성/곡 추가/삭제
- AI 큐레이션 미리보기 및 플레이리스트 저장
- 업로드 시 LUFS 분석 후 -14 LUFS 재생 보정

## SQL
기존 DB에는 `supabase/busy_chart_v1_2_loudness_playlist_patch.sql`를 실행하세요.
새 DB는 `supabase/busy_chart_v1_schema.sql` 전체 실행.

## 주의
MP3 디코딩은 호스팅 환경의 `soundfile/libsndfile` 지원 여부에 따라 실패할 수 있습니다. 실패해도 업로드는 유지되고, 해당 곡은 LUFS 보정 N/A로 표시됩니다.
