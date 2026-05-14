# Busy Chart v1.0.3 Layout + Chart Like Patch

변경 내용:
- 기존 Suno Chart형 구조를 유지하면서 레이아웃을 3영역으로 재배치
  - 왼쪽: 차트
  - 가운데: 플레이 정보 / 앨범 이미지 / 가사 / 재생 컨트롤 / -14 LUFS
  - 오른쪽: 플레이리스트 저장/불러오기 + 현재 플레이리스트
- 차트 테이블 컬럼 폭 축소 및 불필요 컬럼 정리로 오른쪽 잘림 완화
- 차트 안 좋아요 버튼 추가
- 좋아요는 Supabase RPC로 즉시 반영되어 카운트가 바로 갱신됨
- 비로그인 사용자도 기존처럼 차트 재생/일시정지 및 좋아요 가능

적용 후 Supabase SQL Editor에서 아래 파일을 실행하세요.

```sql
supabase/busy_chart_v1_3_layout_like_patch.sql
```

새로 세팅하는 경우에는 `busy_chart_v1_schema.sql`만 실행해도 v1.0.3 RPC가 포함되어 있습니다.
