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

-- Busy Chart v1.0.3: browser-side chart like toggle
create or replace function public.bc_toggle_song_like(p_song_id uuid, p_actor_key text)
returns jsonb
language plpgsql
security definer
as $$
declare
  v_existing uuid;
  v_liked boolean;
  v_like_count int;
begin
  if p_song_id is null or p_actor_key is null or length(trim(p_actor_key)) < 6 then
    return jsonb_build_object('ok', false, 'reason', 'bad_request', 'liked', false, 'like_count', 0);
  end if;

  select id into v_existing
    from public.bc_song_likes
   where song_id = p_song_id and actor_key = p_actor_key
   limit 1;

  if v_existing is not null then
    delete from public.bc_song_likes where id = v_existing;
    v_liked := false;
  else
    insert into public.bc_song_likes(song_id, actor_key, session_id)
    values (p_song_id, p_actor_key, p_actor_key)
    on conflict (song_id, actor_key) do nothing;
    v_liked := true;
  end if;

  perform public.bc_refresh_song_counts(p_song_id);
  select like_count into v_like_count from public.bc_songs where id = p_song_id;

  return jsonb_build_object('ok', true, 'liked', v_liked, 'like_count', coalesce(v_like_count, 0));
end;
$$;

grant execute on function public.bc_toggle_song_like(uuid, text) to anon, authenticated;
-- Busy Chart v1.0.4: browser-side playlist RPCs for the right playlist panel
-- Run this in Supabase SQL Editor after the base Busy Chart schema.

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

create table if not exists public.bc_playlist_items (
  id uuid primary key default gen_random_uuid(),
  playlist_id uuid not null references public.bc_playlists(id) on delete cascade,
  song_id uuid not null references public.bc_songs(id) on delete cascade,
  position integer default 0,
  added_at timestamptz default now(),
  unique(playlist_id, song_id)
);

create index if not exists idx_bc_playlists_owner on public.bc_playlists(owner_user_id, updated_at desc);
create index if not exists idx_bc_playlist_items_playlist on public.bc_playlist_items(playlist_id, position, added_at);

create or replace function public.cloud_list_playlists(p_token text)
returns table(id uuid, name text, song_count bigint, updated_at timestamptz)
language sql
security definer
as $$
  select p.id, p.name, count(i.song_id) as song_count, p.updated_at
    from public.bc_playlists p
    left join public.bc_playlist_items i on i.playlist_id = p.id
   where p.owner_user_id = p_token
     and p.status = 'active'
   group by p.id, p.name, p.updated_at
   order by p.updated_at desc;
$$;

create or replace function public.cloud_save_playlist(p_token text, p_name text, p_song_ids text[])
returns jsonb
language plpgsql
security definer
as $$
declare
  v_playlist_id uuid;
  v_song_id text;
  v_pos integer := 0;
  v_count integer := 0;
begin
  if p_token is null or length(trim(p_token)) < 3 then
    return jsonb_build_object('ok', false, 'message', 'bad token', 'song_count', 0);
  end if;
  if p_name is null or length(trim(p_name)) = 0 then
    p_name := 'Busy Playlist';
  end if;

  insert into public.bc_playlists(owner_user_id, name, description, visibility, status)
  values (p_token, left(trim(p_name), 80), '', 'private', 'active')
  returning id into v_playlist_id;

  if p_song_ids is not null then
    foreach v_song_id in array p_song_ids loop
      if v_song_id is not null and length(trim(v_song_id)) > 0 then
        v_pos := v_pos + 1;
        insert into public.bc_playlist_items(playlist_id, song_id, position)
        values (v_playlist_id, v_song_id::uuid, v_pos)
        on conflict (playlist_id, song_id) do nothing;
      end if;
    end loop;
  end if;

  select count(*) into v_count from public.bc_playlist_items where playlist_id = v_playlist_id;
  update public.bc_playlists set updated_at = now() where id = v_playlist_id;
  return jsonb_build_object('ok', true, 'id', v_playlist_id, 'song_count', v_count);
end;
$$;

create or replace function public.cloud_get_playlist_song_ids(p_token text, p_playlist_id uuid)
returns table(song_id text, position integer)
language sql
security definer
as $$
  select i.song_id::text, coalesce(i.position, 0) as position
    from public.bc_playlist_items i
    join public.bc_playlists p on p.id = i.playlist_id
   where p.id = p_playlist_id
     and p.owner_user_id = p_token
     and p.status = 'active'
   order by i.position, i.added_at;
$$;

create or replace function public.cloud_delete_playlist(p_token text, p_playlist_id uuid)
returns jsonb
language plpgsql
security definer
as $$
begin
  delete from public.bc_playlists
   where id = p_playlist_id
     and owner_user_id = p_token;
  return jsonb_build_object('ok', true);
end;
$$;

grant execute on function public.cloud_list_playlists(text) to anon, authenticated;
grant execute on function public.cloud_save_playlist(text, text, text[]) to anon, authenticated;
grant execute on function public.cloud_get_playlist_song_ids(text, uuid) to anon, authenticated;
grant execute on function public.cloud_delete_playlist(text, uuid) to anon, authenticated;
