-- Preferences learned from each user's ratings and statuses, plus the ones they wrote themselves. A deleted lesson
-- keeps its row with deleted_at set, so it isn't learned again. profiles.lessons_fingerprint identifies the ratings
-- and statuses the lessons were last learned from.
create table public.lessons (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  text text not null check (char_length(text) between 1 and 200),
  source text not null check (source in ('learned', 'user')),
  evidence integer not null default 0,
  confirmed_at timestamptz not null default now(),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index lessons_user_created_idx on public.lessons (user_id, created_at);

create trigger lessons_touch_updated_at
  before update on public.lessons
  for each row execute function public.touch_updated_at();

alter table public.lessons enable row level security;

create policy "own lessons" on public.lessons
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

alter table public.profiles add column lessons_fingerprint text;
