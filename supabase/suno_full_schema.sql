-- Suno Trending: CSV -> Supabase migration schema
-- Run this once in Supabase Dashboard > SQL Editor before running scripts/migrate_csv_to_supabase.py

create extension if not exists pgcrypto;

-- Current active song DB: data/suno_song_db.csv
create table if not exists public.suno_songs (
  id text primary key,
  title text,
  handle text,
  display_name text,
  user_id text,
  created_at timestamptz,
  first_seen_at timestamptz,
  last_checked_at timestamptz,
  play_count integer,
  upvote_count integer,
  comment_count integer,
  flag_count integer,
  is_contest_clip boolean,
  contest_ids text,
  download_disabled_reason text,
  is_public boolean,
  is_hidden boolean,
  is_trashed boolean,
  explicit boolean,
  model text,
  major_model_version text,
  display_tags text,
  duration numeric,
  lyrics text,
  prompt text,
  gpt_description_prompt text,
  song_url text,
  audio_url text,
  image_url text,
  source text,
  effective_comment_count numeric,
  integrated_lufs numeric,
  true_peak_db numeric,
  loudness_gain_db numeric,
  loudness_target_lufs numeric,
  loudness_true_peak_ceiling_db numeric,
  loudness_checked_at timestamptz,
  loudness_status text,
  loudness_error text,
  loudness_audio_url_hash text,
  loudness_input_lra numeric,
  loudness_input_thresh numeric,
  loudness_target_offset numeric,
  adjusted_comment_count numeric,
  comment_quality_ratio numeric,
  analyzed_comment_count integer,
  meaningful_count integer,
  generic_count integer,
  mention_only_count integer,
  emoji_only_count integer,
  comment_quality_summary text,
  comment_quality_checked_at timestamptz,
  current_rank integer,
  previous_rank integer,
  rank_change integer,
  rank_status text,
  current_score numeric,
  base_score numeric,
  growth_score numeric,
  freshness_score numeric,
  best_rank integer,
  best_trend_score numeric,
  best_score_at timestamptz,
  peak_play_count integer,
  peak_upvote_count integer,
  peak_comment_count integer,
  peak_adjusted_comment_count numeric,
  raw jsonb not null default '{}'::jsonb,
  migrated_at timestamptz not null default now()
);

-- Time-series song metrics: data/suno_song_history.csv
create table if not exists public.suno_song_history (
  checked_at timestamptz not null,
  id text not null,
  title text,
  handle text,
  created_at timestamptz,
  play_count integer,
  upvote_count integer,
  comment_count integer,
  flag_count integer,
  raw jsonb not null default '{}'::jsonb,
  migrated_at timestamptz not null default now(),
  primary key (id, checked_at)
);

-- Top 200 rank snapshots: data/suno_rank_history.csv
create table if not exists public.suno_rank_history (
  captured_at timestamptz not null,
  id text not null,
  rank integer,
  trend_score numeric,
  base_score numeric,
  growth_score numeric,
  freshness_score numeric,
  play_count integer,
  upvote_count integer,
  comment_count integer,
  adjusted_comment_count numeric,
  raw jsonb not null default '{}'::jsonb,
  migrated_at timestamptz not null default now(),
  primary key (id, captured_at)
);

-- Archived songs: data/suno_song_archive.csv
create table if not exists public.suno_song_archive (
  id text primary key,
  archived_at timestamptz,
  archive_reason text,
  title text,
  handle text,
  display_name text,
  user_id text,
  created_at timestamptz,
  first_seen_at timestamptz,
  last_checked_at timestamptz,
  play_count integer,
  upvote_count integer,
  comment_count integer,
  adjusted_comment_count numeric,
  comment_quality_ratio numeric,
  meaningful_count integer,
  generic_count integer,
  mention_only_count integer,
  emoji_only_count integer,
  flag_count integer,
  final_rank integer,
  best_rank integer,
  final_trend_score numeric,
  final_base_score numeric,
  final_growth_score numeric,
  final_freshness_score numeric,
  best_trend_score numeric,
  best_score_at timestamptz,
  peak_play_count integer,
  peak_upvote_count integer,
  peak_comment_count integer,
  peak_adjusted_comment_count numeric,
  model text,
  major_model_version text,
  display_tags text,
  duration numeric,
  lyrics text,
  prompt text,
  gpt_description_prompt text,
  song_url text,
  audio_url text,
  image_url text,
  source text,
  raw jsonb not null default '{}'::jsonb,
  migrated_at timestamptz not null default now()
);

-- Manual add queue: data/manual_song_queue.csv
create table if not exists public.manual_song_queue (
  request_id text primary key,
  submitted_at timestamptz,
  url text,
  status text,
  song_id text,
  title text,
  processed_at timestamptz,
  error text,
  raw jsonb not null default '{}'::jsonb,
  migrated_at timestamptz not null default now()
);

-- Replacement for data/suno_app_payload.json / suno_app_payload.zip
create table if not exists public.app_payloads (
  key text primary key,
  payload_json jsonb not null,
  updated_at timestamptz not null default now(),
  source text,
  meta jsonb not null default '{}'::jsonb
);

create index if not exists idx_suno_songs_created_at on public.suno_songs(created_at desc);
create index if not exists idx_suno_songs_last_checked_at on public.suno_songs(last_checked_at asc nulls first);
create index if not exists idx_suno_songs_current_rank on public.suno_songs(current_rank asc nulls last);
create index if not exists idx_suno_songs_handle on public.suno_songs(handle);
create index if not exists idx_song_history_checked_at on public.suno_song_history(checked_at desc);
create index if not exists idx_rank_history_captured_at on public.suno_rank_history(captured_at desc);

-- Optional convenience view for active Top 200 ordered by current_rank.
create or replace view public.v_suno_top200_current as
select *
from public.suno_songs
where current_rank is not null
order by current_rank asc;
