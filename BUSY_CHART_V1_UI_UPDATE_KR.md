# Busy Chart v1.0 UI Update

## 반영 내용

- 기존 뉴트럴 톤 유지
- 일부 남아 있던 구버전/설명형 UI 문구 정리
- 차트 영역을 음악 플랫폼형 리스트 UI로 변경
- 순위, 커버, 곡 정보, 반응 수치, 액션 버튼을 한 줄 중심으로 표시
- 모바일에서는 과도하게 잘리지 않도록 줄/카드형으로 자연스럽게 축소
- 현재 재생 중인 곡 영역을 차트 상단에 표시
- Streamlit 기본 메뉴/헤더/푸터/툴바 숨김 유지
- 플레이어 색감도 현재 뉴트럴 톤에 맞게 조정

## 적용 파일

아래 파일을 기존 저장소에 덮어씌우면 됩니다.

- app.py
- app_modules/busy_player.py
- app_modules/busy_supabase.py
- supabase/busy_chart_v1_schema.sql
- supabase/busy_chart_v1_1_profile_patch.sql
- requirements.txt

## SQL

이미 Busy Chart v1.0 스키마를 실행했고 프로필 확장 패치도 실행했다면 추가 SQL은 필요 없습니다.
처음부터 새로 만들 경우에는 Supabase SQL Editor에서 `supabase/busy_chart_v1_schema.sql`을 실행하세요.

## 참고

이번 ZIP은 새 Busy Chart v1.0에 필요한 핵심 파일만 담았습니다. 기존 Suno 수집 관련 파일들은 앱에서 사용하지 않습니다.
