# Busy Chart v1.0.4 layout + playlist fix

## 변경 사항
- 상단 `내 아이디` 메뉴를 네비게이션에서 제거하고 우측 상단 프로필 드롭다운으로 이동
- 3분할 구조 유지: 차트 / 플레이 정보 / 플레이리스트
- 차트 컬럼을 압축해 오른쪽 잘림 완화
- 좋아요 버튼을 차트 반응 컬럼 안에서 바로 누르고 즉시 카운팅
- 플레이 정보 패널에서 가사창을 하단으로 이동하고 남는 높이까지 확장
- 오른쪽 플레이리스트 저장/불러오기/삭제가 Supabase `bc_playlists`와 연동되도록 RPC 추가

## 적용 후 SQL
Supabase SQL Editor에서 실행:

```sql
supabase/busy_chart_v1_4_layout_playlist_patch.sql
```

처음부터 새로 설치하는 경우 `busy_chart_v1_schema.sql`에도 포함되어 있습니다.
