# Phase2 Direct Cloud Playlist RPC

이번 버전은 Streamlit rerun으로 플레이리스트를 저장/불러오지 않습니다.
JS 플레이어 안에서 Supabase RPC를 직접 호출해서 재생 중인 오디오가 끊기는 문제를 줄입니다.

## 1. Supabase SQL 실행

Supabase Dashboard → SQL Editor에서 아래 파일 내용을 실행하세요.

```text
supabase/playlist_rpc.sql
```

이 SQL은 다음을 추가합니다.

- `user_profiles.playlist_cloud_token`
- `cloud_save_playlist()`
- `cloud_list_playlists()`
- `cloud_get_playlist_song_ids()`
- `cloud_delete_playlist()`

## 2. Streamlit Secrets에 anon key 추가

기존 Secrets에 아래 값을 추가해야 합니다.

```toml
SUPABASE_ANON_KEY = "Supabase anon public key"
```

기존 값은 그대로 유지합니다.

```toml
SUPABASE_URL = "https://프로젝트.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "service_role_secret_key"
SUPABASE_ANON_KEY = "anon_public_key"
```

`SUPABASE_ANON_KEY`는 Supabase Dashboard → Project Settings → API → Project API keys → anon public 에 있습니다.

## 3. 적용 후 확인

1. GitHub에 덮어쓰기 후 push
2. Streamlit Reboot
3. Google 로그인
4. 곡을 플레이리스트에 추가
5. JS 플레이어 안의 Cloud Playlist에서 저장
6. 바로 아래 select box에서 저장된 목록 확인
7. 불러오기/삭제 테스트

## 왜 이 구조로 바꿨나

이전 버전은 `Streamlit 버튼 → Python → Supabase → rerun → JS localStorage` 구조였습니다.
Streamlit은 버튼을 누를 때마다 앱 전체를 다시 실행하므로, HTML 오디오 플레이어가 리마운트되어 재생이 끊길 수 있습니다.

이번 버전은 `JS 플레이어 → Supabase RPC` 구조라서 저장/불러오기/삭제가 Streamlit rerun을 만들지 않습니다.
