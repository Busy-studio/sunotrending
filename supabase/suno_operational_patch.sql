-- Suno Chart Supabase 운영 전환 보조 SQL
-- CSV 직접 업로드용 RAW 테이블을 이미 만들고 업로드한 뒤 실행해도 안전합니다.
-- 핵심 방향:
-- - suno_songs는 전체 곡 보관 테이블로 유지합니다.
-- - 4일 지난 곡은 별도 archive 이동하지 않고, payload/랭킹 생성 시 필터로 제외합니다.
-- - app_payloads.latest를 앱 차트 표시용 캐시로 사용합니다.

create table if not exists public.app_payloads (
  key text primary key,
  payload_json text,
  updated_at timestamptz default now()
);

-- RAW import 테이블이 없으면 최소 형태로 만듭니다. 이미 있으면 아무 것도 지우지 않습니다.
create table if not exists public.suno_songs (id text);
create table if not exists public.suno_song_history (id text);
create table if not exists public.suno_rank_history (id text);
create table if not exists public.manual_song_queue (request_id text);
create table if not exists public.suno_song_archive (id text);

-- 운영 중 스크립트가 쓰는 주요 컬럼 보강. 전부 text라 CSV import/업데이트 타입 오류를 피합니다.
alter table public.suno_songs
  add column if not exists title text,
  add column if not exists handle text,
  add column if not exists display_name text,
  add column if not exists user_id text,
  add column if not exists created_at text,
  add column if not exists first_seen_at text,
  add column if not exists last_checked_at text,
  add column if not exists play_count text,
  add column if not exists upvote_count text,
  add column if not exists comment_count text,
  add column if not exists flag_count text,
  add column if not exists is_contest_clip text,
  add column if not exists contest_ids text,
  add column if not exists download_disabled_reason text,
  add column if not exists is_public text,
  add column if not exists is_hidden text,
  add column if not exists is_trashed text,
  add column if not exists explicit text,
  add column if not exists model text,
  add column if not exists major_model_version text,
  add column if not exists display_tags text,
  add column if not exists duration text,
  add column if not exists lyrics text,
  add column if not exists prompt text,
  add column if not exists gpt_description_prompt text,
  add column if not exists song_url text,
  add column if not exists audio_url text,
  add column if not exists image_url text,
  add column if not exists source text,
  add column if not exists effective_comment_count text,
  add column if not exists integrated_lufs text,
  add column if not exists true_peak_db text,
  add column if not exists loudness_gain_db text,
  add column if not exists loudness_target_lufs text,
  add column if not exists loudness_true_peak_ceiling_db text,
  add column if not exists loudness_checked_at text,
  add column if not exists loudness_status text,
  add column if not exists loudness_error text,
  add column if not exists loudness_audio_url_hash text,
  add column if not exists loudness_input_lra text,
  add column if not exists loudness_input_thresh text,
  add column if not exists loudness_target_offset text,
  add column if not exists adjusted_comment_count text,
  add column if not exists comment_quality_ratio text,
  add column if not exists analyzed_comment_count text,
  add column if not exists meaningful_count text,
  add column if not exists generic_count text,
  add column if not exists mention_only_count text,
  add column if not exists emoji_only_count text,
  add column if not exists comment_quality_summary text,
  add column if not exists comment_quality_checked_at text,
  add column if not exists current_rank text,
  add column if not exists previous_rank text,
  add column if not exists rank_change text,
  add column if not exists rank_status text,
  add column if not exists current_score text,
  add column if not exists base_score text,
  add column if not exists growth_score text,
  add column if not exists freshness_score text,
  add column if not exists best_rank text,
  add column if not exists best_trend_score text,
  add column if not exists best_score_at text,
  add column if not exists peak_play_count text,
  add column if not exists peak_upvote_count text,
  add column if not exists peak_comment_count text,
  add column if not exists peak_adjusted_comment_count text;

alter table public.suno_song_history
  add column if not exists checked_at text,
  add column if not exists title text,
  add column if not exists handle text,
  add column if not exists created_at text,
  add column if not exists play_count text,
  add column if not exists upvote_count text,
  add column if not exists comment_count text,
  add column if not exists flag_count text;

alter table public.suno_rank_history
  add column if not exists captured_at text,
  add column if not exists rank text,
  add column if not exists trend_score text,
  add column if not exists base_score text,
  add column if not exists growth_score text,
  add column if not exists freshness_score text,
  add column if not exists play_count text,
  add column if not exists upvote_count text,
  add column if not exists comment_count text,
  add column if not exists adjusted_comment_count text;

alter table public.manual_song_queue
  add column if not exists submitted_at text,
  add column if not exists url text,
  add column if not exists status text,
  add column if not exists song_id text,
  add column if not exists title text,
  add column if not exists processed_at text,
  add column if not exists error text;

create index if not exists idx_suno_songs_id on public.suno_songs(id);
create index if not exists idx_suno_songs_handle on public.suno_songs(handle);
create index if not exists idx_suno_song_history_id on public.suno_song_history(id);
create index if not exists idx_suno_rank_history_id on public.suno_rank_history(id);

-- 확인용
select 'suno_songs' as table_name, count(*) from public.suno_songs
union all select 'suno_song_history', count(*) from public.suno_song_history
union all select 'suno_rank_history', count(*) from public.suno_rank_history
union all select 'manual_song_queue', count(*) from public.manual_song_queue
union all select 'app_payloads', count(*) from public.app_payloads;
