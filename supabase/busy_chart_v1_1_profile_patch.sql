
-- Busy Chart v1.0.1 profile extension
alter table public.bc_profiles add column if not exists bio text;
alter table public.bc_profiles add column if not exists suno_url text;
alter table public.bc_profiles add column if not exists spotify_url text;
alter table public.bc_profiles add column if not exists youtube_url text;
alter table public.bc_profiles add column if not exists instagram_url text;
alter table public.bc_profiles add column if not exists website_url text;
