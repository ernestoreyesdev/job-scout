-- Core schema for job-finder.
--
-- Per-user tables belong to auth.uid() and row-level security keeps each user
-- to their own rows, so the anon key is safe to ship in the web client.
-- Postings are shared: every signed-in user can read them, and only the agent
-- (service role) writes them.

create function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create table public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  -- Last 4 characters of the stored Anthropic key, for display only.
  anthropic_key_hint text,
  updated_at timestamptz not null default now()
);

-- Encrypted third-party keys. RLS is on with no policies, so only the
-- service role (the agent) can read or write them.
create table public.api_credentials (
  user_id uuid not null references auth.users (id) on delete cascade,
  provider text not null,
  ciphertext text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, provider)
);

create table public.resumes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  -- Object path inside the private `resumes` bucket: {user_id}/{file}.
  storage_path text not null,
  file_name text not null,
  -- Plain text extracted by the agent; null until extraction runs.
  text text,
  is_primary boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index resumes_one_primary_idx on public.resumes (user_id) where is_primary;

create type public.job_source as enum ('greenhouse', 'lever', 'ashby');

create table public.postings (
  id uuid primary key default gen_random_uuid(),
  source public.job_source not null,
  -- Board or company token on the source, e.g. a Greenhouse board token.
  board text not null,
  external_id text not null,
  title text not null,
  company text not null,
  location text,
  url text not null,
  description text not null default '',
  posted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source, external_id)
);

create type public.application_status as enum (
  'new', 'saved', 'tailored', 'applied', 'interviewing', 'rejected'
);

-- The tracker: one row per user and posting, holding the fit score and progress.
create table public.applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  posting_id uuid not null references public.postings (id) on delete cascade,
  resume_id uuid references public.resumes (id) on delete set null,
  fit_score integer check (fit_score between 0 and 100),
  fit_summary text,
  strengths jsonb not null default '[]',
  gaps jsonb not null default '[]',
  status public.application_status not null default 'new',
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, posting_id)
);

create index applications_user_score_idx on public.applications (user_id, fit_score desc);

create type public.run_status as enum ('queued', 'running', 'done', 'failed');

create table public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  kind text not null,
  input jsonb not null default '{}',
  status public.run_status not null default 'queued',
  error text,
  -- Token counts summed across every model call in the run.
  usage jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finished_at timestamptz
);

create index agent_runs_user_created_idx on public.agent_runs (user_id, created_at desc);

create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute function public.touch_updated_at();

create trigger api_credentials_touch_updated_at
  before update on public.api_credentials
  for each row execute function public.touch_updated_at();

create trigger resumes_touch_updated_at
  before update on public.resumes
  for each row execute function public.touch_updated_at();

create trigger postings_touch_updated_at
  before update on public.postings
  for each row execute function public.touch_updated_at();

create trigger applications_touch_updated_at
  before update on public.applications
  for each row execute function public.touch_updated_at();

create trigger agent_runs_touch_updated_at
  before update on public.agent_runs
  for each row execute function public.touch_updated_at();

alter table public.profiles enable row level security;
alter table public.api_credentials enable row level security;
alter table public.resumes enable row level security;
alter table public.postings enable row level security;
alter table public.applications enable row level security;
alter table public.agent_runs enable row level security;

create policy "own profile" on public.profiles
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own resumes" on public.resumes
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "signed-in users read postings" on public.postings
  for select to authenticated using (true);

create policy "own applications" on public.applications
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own agent runs" on public.agent_runs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Resume files live under resumes/{user_id}/ in a private bucket.
insert into storage.buckets (id, name, public)
values ('resumes', 'resumes', false);

create policy "own resume files" on storage.objects
  for all to authenticated
  using (bucket_id = 'resumes' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'resumes' and (storage.foldername(name))[1] = auth.uid()::text);
