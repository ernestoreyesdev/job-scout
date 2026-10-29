-- Workplace type normalized across sources; null when the source doesn't say.
create type public.workplace_type as enum ('onsite', 'hybrid', 'remote');

alter table public.postings add column workplace_type public.workplace_type;

-- Shared directory of job boards the agent has confirmed, from company lookups
-- and web discovery. Every signed-in user reads it; only the agent writes it.
create type public.company_origin as enum ('lookup', 'discovery');

create table public.companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  source public.job_source not null,
  board text not null,
  open_jobs integer not null default 0,
  found_by public.company_origin not null,
  checked_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (source, board)
);

alter table public.companies enable row level security;

create policy "signed-in users read companies" on public.companies
  for select to authenticated using (true);
