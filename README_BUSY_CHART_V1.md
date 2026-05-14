# Busy Chart v1.0

마지막 Suno Chart UI/플레이어 구조를 기반으로, 데이터 소스만 사용자 업로드곡으로 바꾼 Streamlit + Supabase 버전입니다.

## 적용
1. main 브랜치에 덮어쓰기
2. Supabase SQL Editor에서 `supabase/busy_chart_v1_schema.sql` 실행
3. Streamlit Secrets에 아래 값 설정

```toml
SUPABASE_URL = "https://...supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "..."
SUPABASE_ANON_KEY = "..."
```

## Storage buckets
SQL에서 자동 생성 시도합니다. 실패 시 Supabase Storage에서 public bucket으로 직접 생성하세요.
- busy-audio
- busy-cover
- busy-avatar

## 핵심
- 기존 Suno Chart 스타일의 좌측 플레이어 + 우측 차트 테이블 유지
- Busy Chart 뉴트럴 톤 적용
- 상단 메뉴: 차트 / 플레이리스트 / AI 큐레이션 / 내 아이디
- 사용자가 업로드한 MP3/커버 이미지가 바로 차트에 반영
- 30% 이상 재생 시 play count 반영
- 좋아요, 댓글, 댓글 좋아요, 플레이리스트, 프로필, 업로드 관리 지원
- -14 LUFS 분석 값이 있는 경우 기존 플레이어의 LUFS 정규화 버튼 사용
