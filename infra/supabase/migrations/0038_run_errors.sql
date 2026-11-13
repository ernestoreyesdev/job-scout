-- The original error behind a run that failed unexpectedly; the run itself shows the user a plain message. RLS is on
-- with no policies, so only the service role (the agent) can read or write it.
create table public.run_errors (
  run_id uuid primary key references public.agent_runs (id) on delete cascade,
  detail text not null,
  created_at timestamptz not null default now()
);

create index run_errors_created_at on public.run_errors (created_at);

alter table public.run_errors enable row level security;
