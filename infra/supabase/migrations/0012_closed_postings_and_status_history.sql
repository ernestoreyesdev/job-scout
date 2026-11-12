-- When a posting was last seen missing from its board; null while it's listed.
alter table public.postings add column closed_at timestamptz;

-- Every status a tracked job has had, with when it changed.
create table public.application_events (
  id uuid primary key default gen_random_uuid(),
  application_id uuid not null references public.applications (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  status public.application_status not null,
  changed_at timestamptz not null default now()
);

create index application_events_application_idx on public.application_events (application_id, changed_at);

alter table public.application_events enable row level security;

create policy "own application events" on public.application_events
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Records the status of every new job and every status change.
create function public.record_application_status()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'INSERT' or new.status is distinct from old.status then
    insert into public.application_events (application_id, user_id, status)
    values (new.id, new.user_id, new.status);
  end if;
  return new;
end;
$$;

create trigger applications_record_status
  after insert or update of status on public.applications
  for each row execute function public.record_application_status();

-- Existing jobs: when they were added, and their current status as of their last update.
insert into public.application_events (application_id, user_id, status, changed_at)
select id, user_id, 'new', created_at from public.applications;

insert into public.application_events (application_id, user_id, status, changed_at)
select id, user_id, status, updated_at from public.applications where status <> 'new';
