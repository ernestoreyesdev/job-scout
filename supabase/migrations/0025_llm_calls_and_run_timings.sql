-- One row per Claude call: the step that made it, its tokens, how long it took and how it ended. RLS is on with no
-- policies, so only the service role (the agent) can read or write it.
create table public.llm_calls (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references public.agent_runs (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  step text not null,
  model text not null,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cache_read_input_tokens integer not null default 0,
  cache_creation_input_tokens integer not null default 0,
  web_search_requests integer not null default 0,
  duration_ms integer not null,
  stop_reason text,
  error text,
  created_at timestamptz not null default now()
);

create index llm_calls_created_at on public.llm_calls (created_at);
create index llm_calls_run_id on public.llm_calls (run_id);

alter table public.llm_calls enable row level security;

-- Milliseconds each step of a run took, by step name.
alter table public.agent_runs add column timings jsonb;
