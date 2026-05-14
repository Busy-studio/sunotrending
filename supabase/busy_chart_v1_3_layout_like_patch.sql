-- Busy Chart v1.0.3: chart-like RPC for anonymous/session likes
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
