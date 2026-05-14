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
