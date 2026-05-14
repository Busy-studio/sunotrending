-- Busy Chart v1.0.2 patch: -14 LUFS playback metadata + playlists
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
