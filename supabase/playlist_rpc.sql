-- Phase2 Direct JS Playlist RPC migration
-- Run this once in Supabase SQL Editor after supabase/schema.sql.
-- It lets the browser player save/load/delete playlists without triggering Streamlit reruns.

alter table if exists public.user_profiles
  add column if not exists playlist_cloud_token text unique;

-- Keep direct table access closed for anon/authenticated clients.
-- The browser calls only the SECURITY DEFINER RPC functions below.
alter table if exists public.user_profiles enable row level security;
alter table if exists public.playlists enable row level security;
alter table if exists public.playlist_items enable row level security;

revoke all on table public.user_profiles from anon, authenticated;
revoke all on table public.playlists from anon, authenticated;
revoke all on table public.playlist_items from anon, authenticated;

create or replace function public.cloud_save_playlist(
  p_token text,
  p_name text,
  p_song_ids text[]
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id text;
  v_playlist_id uuid;
  v_name text;
  v_song_count integer;
begin
  select user_id into v_user_id
  from public.user_profiles
  where playlist_cloud_token = p_token;

  if v_user_id is null then
    raise exception 'invalid playlist token';
  end if;

  v_name := nullif(trim(coalesce(p_name, '')), '');
  if v_name is null then
    v_name := 'My Playlist';
  end if;

  insert into public.playlists(user_id, name, visibility, updated_at)
  values (v_user_id, v_name, 'private', now())
  returning id into v_playlist_id;

  insert into public.playlist_items(playlist_id, song_id, position)
  select v_playlist_id, song_id, ordinality::integer - 1
  from unnest(coalesce(p_song_ids, array[]::text[])) with ordinality as u(song_id, ordinality)
  where nullif(trim(song_id), '') is not null
  on conflict (playlist_id, song_id) do nothing;

  select count(*)::integer into v_song_count
  from public.playlist_items
  where playlist_id = v_playlist_id;

  return jsonb_build_object(
    'id', v_playlist_id,
    'name', v_name,
    'song_count', coalesce(v_song_count, 0)
  );
end;
$$;

create or replace function public.cloud_list_playlists(p_token text)
returns table(
  id uuid,
  name text,
  created_at timestamptz,
  updated_at timestamptz,
  song_count bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id text;
begin
  select user_id into v_user_id
  from public.user_profiles
  where playlist_cloud_token = p_token;

  if v_user_id is null then
    raise exception 'invalid playlist token';
  end if;

  return query
  select
    p.id,
    p.name,
    p.created_at,
    p.updated_at,
    count(pi.id)::bigint as song_count
  from public.playlists p
  left join public.playlist_items pi on pi.playlist_id = p.id
  where p.user_id = v_user_id
  group by p.id, p.name, p.created_at, p.updated_at
  order by p.updated_at desc nulls last, p.created_at desc;
end;
$$;

drop function if exists public.cloud_get_playlist_song_ids(text, uuid);

create or replace function public.cloud_get_playlist_song_ids(
  p_token text,
  p_playlist_id uuid
)
returns table(song_id text, item_position integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id text;
begin
  select user_id into v_user_id
  from public.user_profiles
  where playlist_cloud_token = p_token;

  if v_user_id is null then
    raise exception 'invalid playlist token';
  end if;

  if not exists (
    select 1 from public.playlists
    where id = p_playlist_id and user_id = v_user_id
  ) then
    raise exception 'playlist not found';
  end if;

  return query
  select pi.song_id, pi.position as item_position
  from public.playlist_items pi
  where pi.playlist_id = p_playlist_id
  order by pi.position asc, pi.added_at asc;
end;
$$;

create or replace function public.cloud_delete_playlist(
  p_token text,
  p_playlist_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id text;
begin
  select user_id into v_user_id
  from public.user_profiles
  where playlist_cloud_token = p_token;

  if v_user_id is null then
    raise exception 'invalid playlist token';
  end if;

  delete from public.playlists
  where id = p_playlist_id and user_id = v_user_id;

  return found;
end;
$$;

revoke all on function public.cloud_save_playlist(text, text, text[]) from public;
revoke all on function public.cloud_list_playlists(text) from public;
revoke all on function public.cloud_get_playlist_song_ids(text, uuid) from public;
revoke all on function public.cloud_delete_playlist(text, uuid) from public;

grant execute on function public.cloud_save_playlist(text, text, text[]) to anon, authenticated;
grant execute on function public.cloud_list_playlists(text) to anon, authenticated;
grant execute on function public.cloud_get_playlist_song_ids(text, uuid) to anon, authenticated;
grant execute on function public.cloud_delete_playlist(text, uuid) to anon, authenticated;
