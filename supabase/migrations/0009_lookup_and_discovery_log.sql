-- Why a run failed, in a form the app can act on (e.g. 'company_not_found').
alter table public.agent_runs add column error_code text;

-- Each time web discovery ran to grow the shared directory. Only the agent writes it.
create table public.directory_discoveries (
  id uuid primary key default gen_random_uuid(),
  ran_at timestamptz not null default now(),
  keywords text[] not null default '{}',
  boards_found integer not null default 0,
  boards_added integer not null default 0
);

alter table public.directory_discoveries enable row level security;
