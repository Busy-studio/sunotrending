# 기존 Suno 수집 파일 정리 참고

Busy Chart v1.0은 사용자 업로드곡 기반이므로 아래 파일/폴더는 더 이상 앱 실행에 필요하지 않습니다.
덮어쓰기만 하면 기존 파일이 남을 수 있으니, 저장소를 깔끔하게 정리하고 싶을 때 수동 삭제하세요.

- scripts/ 전체 Suno 수집/마이그레이션 스크립트
- app_modules/data_loader.py
- app_modules/manual_queue.py
- app_modules/player_component.py
- app_modules/supabase_chart_loader.py
- app_modules/supabase_store.py
- app_modules/playlist_bridge/
- data/ 안의 suno_*.zip
- config/rain_crew.json
- .github/workflows_disabled/
- 기존 Suno 관련 README/PHASE/SUPABASE 마이그레이션 문서

단, 혹시 롤백 가능성을 남기고 싶으면 삭제하지 않아도 됩니다. 현재 app.py는 Busy Chart 전용 모듈만 import합니다.
