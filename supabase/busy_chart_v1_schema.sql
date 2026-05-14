-- Busy Chart v1.0 schema
-- Run this in Supabase SQL Editor before using the app.

create extension if not exists pgcrypto;

-- Storage buckets. If bucket creation is blocked by policy, create these manually in Storage UI.
insert into storage.buckets (id, name, public)
values
  ('busy-audio', 'busy-audio', true),
  ('busy-cover', 'busy-cover', true),
  ('busy-avatar', 'busy-avatar', true)
on conflict (id) do update set public = excluded.public;

create table if not exists public.bc_profiles (
  user_id text primary key,
  email text,
  display_name text,
  avatar_path text,
  avatar_url text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  last_login_at timestamptz
);

create table if not exists public.bc_songs (
  id uuid primary key default gen_random_uuid(),
  uploader_user_id text not null references public.bc_profiles(user_id) on delete cascade,
  title text not null,
  artist_name text,
  description text,
  style_tags text,
  lyrics text,
  audio_path text,
  audio_url text,
  cover_path text,
  cover_url text,
  comments_enabled boolean not null default true,
  visibility text not null default 'public',
  status text not null default 'active',
  rights_confirmed boolean not null default false,
  rights_confirmed_at timestamptz,
  play_count integer not null default 0,
  like_count integer not null default 0,
  comment_count integer not null default 0,
  trend_score numeric not null default 0,
  integrated_lufs numeric,
  true_peak_db numeric,
  loudness_gain_db numeric,
  loudness_target_lufs numeric default -14.0,
  loudness_true_peak_ceiling_db numeric default -1.0,
  loudness_checked_at timestamptz,
  loudness_status text,
  loudness_error text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_bc_songs_public_score on public.bc_songs(status, visibility, trend_score desc, created_at desc);
create index if not exists idx_bc_songs_uploader on public.bc_songs(uploader_user_id, created_at desc);

create table if not exists public.bc_song_likes (
  id uuid primary key default gen_random_uuid(),
  song_id uuid not null references public.bc_songs(id) on delete cascade,
  actor_key text not null,
  user_id text,
  session_id text,
  created_at timestamptz default now(),
  unique(song_id, actor_key)
);
create index if not exists idx_bc_song_likes_song on public.bc_song_likes(song_id);

create table if not exists public.bc_play_events (
  id uuid primary key default gen_random_uuid(),
  song_id uuid not null references public.bc_songs(id) on delete cascade,
  session_id text,
  user_id text,
  play_seconds integer default 0,
  counted_at timestamptz default now(),
  unique(song_id, session_id)
);
create index if not exists idx_bc_play_events_song on public.bc_play_events(song_id);

create table if not exists public.bc_comments (
  id uuid primary key default gen_random_uuid(),
  song_id uuid not null references public.bc_songs(id) on delete cascade,
  user_id text not null,
  display_name text,
  body text not null,
  status text not null default 'visible',
  like_count integer not null default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists idx_bc_comments_song on public.bc_comments(song_id, created_at desc);

create table if not exists public.bc_comment_likes (
  id uuid primary key default gen_random_uuid(),
  comment_id uuid not null references public.bc_comments(id) on delete cascade,
  actor_key text not null,
  user_id text,
  session_id text,
  created_at timestamptz default now(),
  unique(comment_id, actor_key)
);

create or replace function public.bc_calc_score(p_play int, p_like int, p_comment int, p_created timestamptz)
returns numeric
language sql
stable
as $$
  select round((ln(1 + greatest(p_play,0)) * 1.0
    + ln(1 + greatest(p_like,0)) * 3.0
    + ln(1 + greatest(p_comment,0)) * 4.0
    + power(greatest(0, 1 - extract(epoch from (now() - p_created)) / (7*24*3600)), 1.25) * 30.0)::numeric, 6)
$$;

create or replace function public.bc_refresh_song_counts(p_song_id uuid)
returns void
language plpgsql
security definer
as $$
declare
  v_likes int;
  v_plays int;
  v_comments int;
  v_created timestamptz;
begin
  select count(*) into v_likes from public.bc_song_likes where song_id = p_song_id;
  select count(*) into v_plays from public.bc_play_events where song_id = p_song_id;
  select count(*) into v_comments from public.bc_comments where song_id = p_song_id and status = 'visible';
  select created_at into v_created from public.bc_songs where id = p_song_id;
  update public.bc_songs
     set like_count = coalesce(v_likes,0),
         play_count = coalesce(v_plays,0),
         comment_count = coalesce(v_comments,0),
         trend_score = public.bc_calc_score(coalesce(v_plays,0), coalesce(v_likes,0), coalesce(v_comments,0), coalesce(v_created, now())),
         updated_at = now()
   where id = p_song_id;
end;
$$;

create or replace function public.bc_record_play(p_song_id uuid, p_session_id text, p_play_seconds int default 0)
returns jsonb
language plpgsql
security definer
as $$
begin
  if p_song_id is null or p_session_id is null or length(trim(p_session_id)) < 6 then
    return jsonb_build_object('ok', false, 'reason', 'bad_request');
  end if;

  insert into public.bc_play_events(song_id, session_id, play_seconds)
  values (p_song_id, p_session_id, greatest(coalesce(p_play_seconds,0),0))
  on conflict (song_id, session_id) do nothing;

  perform public.bc_refresh_song_counts(p_song_id);
  return jsonb_build_object('ok', true);
end;
$$;

grant execute on function public.bc_record_play(uuid, text, int) to anon, authenticated;
grant execute on function public.bc_refresh_song_counts(uuid) to anon, authenticated;

-- For prototype simplicity: Streamlit uses service role for writes. RPC handles browser play events.


-- Busy Chart v1.0.1 profile extension
alter table public.bc_profiles add column if not exists bio text;
alter table public.bc_profiles add column if not exists suno_url text;
alter table public.bc_profiles add column if not exists spotify_url text;
alter table public.bc_profiles add column if not exists youtube_url text;
alter table public.bc_profiles add column if not exists instagram_url text;
alter table public.bc_profiles add column if not exists website_url text;



-- Busy Chart v1.0.2: loudness + playlist extension
alter table public.bc_songs add column if not exists integrated_lufs numeric;
alter table public.bc_songs add column if not exists true_peak_db numeric;
alter table public.bc_songs add column if not exists loudness_gain_db numeric;
alter table public.bc_songs add column if not exists loudness_target_lufs numeric default -14.0;
alter table public.bc_songs add column if not exists loudness_true_peak_ceiling_db numeric default -1.0;
alter table public.bc_songs add column if not exists loudness_checked_at timestamptz;
alter table public.bc_songs add column if not exists loudness_status text;
alter table public.bc_songs add column if not exists loudness_error text;

create table if not exists public.bc_playlists (
  id uuid primary key default gen_random_uuid(),
  owner_user_id text not null references public.bc_profiles(user_id) on delete cascade,
  name text not null,
  description text,
  visibility text not null default 'public',
  status text not null default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists idx_bc_playlists_owner on public.bc_playlists(owner_user_id, updated_at desc);
create index if not exists idx_bc_playlists_public on public.bc_playlists(visibility, status, updated_at desc);

create table if not exists public.bc_playlist_items (
  id uuid primary key default gen_random_uuid(),
  playlist_id uuid not null references public.bc_playlists(id) on delete cascade,
  song_id uuid not null references public.bc_songs(id) on delete cascade,
  position integer default 0,
  added_at timestamptz default now(),
  unique(playlist_id, song_id)
);
create index if not exists idx_bc_playlist_items_playlist on public.bc_playlist_items(playlist_id, position, added_at);
