-- Suno Chart Supabase schema
-- Run this once in Supabase Dashboard > SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.user_profiles (
  user_id text primary key,
  email text,
  name text,
  picture text,
  created_at timestamptz not null default now(),
  last_login_at timestamptz not null default now()
);

create table if not exists public.playlists (
  id uuid primary key default gen_random_uuid(),
  user_id text not null references public.user_profiles(user_id) on delete cascade,
  name text not null default 'My Playlist',
  visibility text not null default 'private' check (visibility in ('private', 'public')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.playlist_items (
  id uuid primary key default gen_random_uuid(),
  playlist_id uuid not null references public.playlists(id) on delete cascade,
  song_id text not null,
  position integer not null default 0,
  added_at timestamptz not null default now(),
  unique (playlist_id, song_id)
);

create table if not exists public.app_likes (
  user_id text not null references public.user_profiles(user_id) on delete cascade,
  song_id text not null,
  liked_at timestamptz not null default now(),
  primary key (user_id, song_id)
);

create table if not exists public.app_play_events (
  id uuid primary key default gen_random_uuid(),
  user_id text references public.user_profiles(user_id) on delete set null,
  song_id text not null,
  session_id text,
  played_at timestamptz not null default now(),
  play_seconds integer not null default 0,
  counted boolean not null default false
);

create table if not exists public.app_song_stats (
  song_id text primary key,
  app_play_count integer not null default 0,
  app_like_count integer not null default 0,
  unique_listener_count integer not null default 0,
  updated_at timestamptz not null default now()
);

create index if not exists idx_playlists_user_id on public.playlists(user_id);
create index if not exists idx_playlist_items_playlist_id on public.playlist_items(playlist_id);
create index if not exists idx_playlist_items_song_id on public.playlist_items(song_id);
create index if not exists idx_app_likes_song_id on public.app_likes(song_id);
create index if not exists idx_app_play_events_song_id on public.app_play_events(song_id);
create index if not exists idx_app_play_events_user_song on public.app_play_events(user_id, song_id);

-- Keep playlist updated_at fresh when playlist rows are edited.
create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists set_playlists_updated_at on public.playlists;
create trigger set_playlists_updated_at
before update on public.playlists
for each row execute function public.set_updated_at();

-- Optional safety: since the Streamlit app uses the service role key server-side,
-- public anon access is not required. Keep RLS enabled by default.
alter table public.user_profiles enable row level security;
alter table public.playlists enable row level security;
alter table public.playlist_items enable row level security;
alter table public.app_likes enable row level security;
alter table public.app_play_events enable row level security;
alter table public.app_song_stats enable row level security;
