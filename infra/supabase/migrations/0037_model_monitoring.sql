-- A fingerprint of the prompt behind each Claude call and each fit score, so quality and cost can be compared before
-- and after a prompt or model change.
alter table public.llm_calls add column prompt_version text;

alter table public.applications
  add column score_model text,
  add column score_prompt_version text;

-- One row per evaluation run, scheduled or by hand, with its results. RLS is on with no policies, so only the agent
-- and the evals (both with the service role) can use it.
create table public.eval_runs (
  id uuid primary key default gen_random_uuid(),
  eval text not null,
  model text,
  prompt_version text,
  metrics jsonb not null default '{}',
  cost numeric,
  created_at timestamptz not null default now()
);

create index eval_runs_created_at on public.eval_runs (created_at desc);

alter table public.eval_runs enable row level security;
