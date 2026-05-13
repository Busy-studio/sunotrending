# Update rotation fix

이 패치는 기존 active 곡 업데이트 누락을 고칩니다.

## 문제
기존 `choose_rows_to_update()`는 `created_at` 최신순으로 `MAX_UPDATE_ROWS`개만 선택했습니다. DB가 `MAX_UPDATE_ROWS`보다 커지면 오래된 active 곡은 매번 선택되지 않아 play/like/comment가 멈춘 값으로 남을 수 있었습니다.

예: `MAX_UPDATE_ROWS=300`, active DB 2,800곡이면 최신 300곡 위주로만 상세 페이지가 갱신됩니다.

## 수정
업데이트 대상을 다음 순서로 선택합니다.

1. `created_at` 누락 곡
2. `last_checked_at`이 없거나 가장 오래된 곡
3. 같은 조건이면 최신 생성곡

따라서 scheduled update가 여러 번 돌면 active DB 전체가 순환 업데이트됩니다.
