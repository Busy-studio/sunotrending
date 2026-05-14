-- Suno Trending Supabase 운영 최적화 패치
-- 반영 내용:
-- 1) suno_songs 전체 보관 + update_tier/next_check_at 기반 조건부 업데이트
-- 2) suno_comments 원문 저장
-- 3) 댓글 품질은 신규 댓글(analyzed_at is null)만 증분 분석
-- 4) app_payloads.payload_json은 jsonb 유지

create table if not exists public.suno_songs (
  id text primary key
);

alter table public.suno_songs
  add column if not exists status text,
  add column if not exists update_tier text,
  add column if not exists next_check_at text,
  add column if not exists fetch_fail_count text,
  add column if not exists last_fetch_error text,
  add column if not exists last_change_at text,
  add column if not exists playlist_ref_count text,
  add column if not exists comments_fetch_needed text,
  add column if not exists last_comment_fetch_at text;

create index if not exists idx_suno_songs_update_tier on public.suno_songs(update_tier);
create index if not exists idx_suno_songs_next_check_at on public.suno_songs(next_check_at);
create index if not exists idx_suno_songs_status on public.suno_songs(status);
create index if not exists idx_suno_songs_last_checked_at on public.suno_songs(last_checked_at);

create table if not exists public.suno_comments (
  comment_id text primary key,
  song_id text not null,
  content text,
  user_id text,
  user_handle text,
  user_display_name text,
  num_likes text,
  num_replies text,
  created_at text,
  fetched_at text,
  is_reply text,
  parent_comment_id text,
  user_mentions_json text,
  quality_label text,
  quality_weight text,
  is_meaningful text,
  is_generic text,
  is_mention_only text,
  is_emoji_only text,
  analyzed_at text
);

create index if not exists idx_suno_comments_song_id on public.suno_comments(song_id);
create index if not exists idx_suno_comments_analyzed_at on public.suno_comments(analyzed_at);
create index if not exists idx_suno_comments_created_at on public.suno_comments(created_at);
create index if not exists idx_suno_comments_quality_label on public.suno_comments(quality_label);

-- app_payloads는 앱 표시용 캐시이므로 jsonb로 유지한다.
drop table if exists public.app_payloads;
create table public.app_payloads (
  key text primary key,
  payload_json jsonb,
  updated_at timestamptz default now()
);

select 'suno_songs' as table_name, count(*) from public.suno_songs
union all select 'suno_comments', count(*) from public.suno_comments
union all select 'app_payloads', count(*) from public.app_payloads;
