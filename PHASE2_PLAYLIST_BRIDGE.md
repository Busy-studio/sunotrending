# Suno Chart Phase 2 - JS Player Cloud Playlist Bridge

이번 버전은 임시 체크박스 저장 방식이 아니라, 기존 `player_component.py`의 JS 플레이어 상태를 기준으로 Supabase 플레이리스트 저장/불러오기 기반을 붙인 버전입니다.

## 추가된 파일

```text
app_modules/playlist_bridge/__init__.py
app_modules/playlist_bridge/frontend/index.html
PHASE2_PLAYLIST_BRIDGE.md
```

## 수정된 파일

```text
app.py
app_modules/player_component.py
```

## 동작 구조

```text
JS 플레이어 localStorage
        ↓
playlist_bridge custom component
        ↓
Streamlit Python
        ↓
Supabase playlists / playlist_items
```

Supabase service role key는 여전히 Python 서버에서만 사용하고, 브라우저 JS에는 노출하지 않습니다.

## 새 기능

### 1. JS 플레이어 안의 Cloud Playlist 저장

왼쪽 플레이어에 `Cloud Playlist` 박스가 추가됩니다.

1. 곡을 플레이리스트에 추가
2. 저장할 이름 입력
3. `저장` 클릭
4. bridge가 JS localStorage 요청을 Python으로 전달
5. Python이 Supabase에 저장

### 2. Cloud Playlist 관리 패널

로그인 + Supabase 설정이 된 경우, 차트 위쪽에 `Cloud Playlist 관리` expander가 보입니다.

가능한 작업:

```text
저장된 플레이리스트 목록 보기
플레이어에 불러오기
삭제
```

`플레이어에 불러오기`는 저장된 song_id를 현재 payload의 곡 정보와 매칭해서 JS 플레이어 localStorage에 다시 넣습니다. 그 다음 플레이어가 같은 렌더링에서 해당 목록을 복원합니다.

## 현재 한계

1. 플레이리스트에는 현재 `song_id`와 순서만 저장합니다.
2. 4일이 지나 payload에서 사라진 곡은 아직 불러오기에서 제외될 수 있습니다.
3. Archive 곡 lookup을 붙이면 오래된 저장곡도 복원 가능해집니다.
4. 좋아요/재생 카운트는 아직 다음 Phase입니다.

## 다음 Phase 추천

```text
Phase 3: archive song lookup 연결 → 오래된 저장곡도 플레이리스트에서 재생
Phase 4: JS 플레이어 좋아요 버튼 → Supabase app_likes
Phase 5: 30초 이상 재생 이벤트 → Supabase app_play_events
Phase 6: Suno 공식 수치 + 앱 내부 수치 보조 반영
```
