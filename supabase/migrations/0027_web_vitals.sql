-- Page load measurements browsers report (TTFB, FCP, LCP, CLS, INP). A signed-in user can only add their own rows;
-- nobody can read them through the API, so only the service role (the agent) sees them.
create table public.web_vitals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  page text not null,
  metric text not null check (metric in ('TTFB', 'FCP', 'LCP', 'CLS', 'INP')),
  value double precision not null,
  rating text,
  navigation_type text,
  created_at timestamptz not null default now()
);

create index web_vitals_created_at on public.web_vitals (created_at);

alter table public.web_vitals enable row level security;

create policy "add own web vitals" on public.web_vitals
  for insert to authenticated with check (auth.uid() = user_id);
