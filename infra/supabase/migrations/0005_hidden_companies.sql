-- Companies a user has hidden from their directory searches.
create table public.hidden_companies (
  user_id uuid not null references auth.users (id) on delete cascade,
  company_id uuid not null references public.companies (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, company_id)
);

alter table public.hidden_companies enable row level security;

create policy "own hidden companies" on public.hidden_companies
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
