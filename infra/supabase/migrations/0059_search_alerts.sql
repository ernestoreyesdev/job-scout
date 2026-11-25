-- Searches a user marked to run each morning after the board refresh, emailing them the new strong matches. `rule` is
-- the search's input, as agent_runs.input stores it.
create table public.search_alerts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  rule jsonb not null,
  created_at timestamptz not null default now(),
  unique (user_id, rule)
);

alter table public.search_alerts enable row level security;

create policy "own search alerts" on public.search_alerts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
