-- Saving jobs compares them with the saved ones first and sends only new, changed and reopened jobs to the upsert,
-- which locks every existing row it's given. Same inputs and outputs as before.
create or replace function public.save_postings(jobs jsonb)
returns table (id uuid, source public.job_source, external_id text, created_at timestamptz)
language sql
set search_path = public
as $$
  with incoming as (
    select * from jsonb_populate_recordset(null::public.postings, jobs)
  ),
  unchanged as (
    select p.id, p.source, p.external_id, p.created_at
    from incoming i
    join public.postings p on p.source = i.source and p.external_id = i.external_id
    where p.closed_at is null
      and (p.board, p.title, p.company, p.location, p.url, p.description, p.posted_at, p.workplace_type)
        is not distinct from (i.board, i.title, i.company, i.location, i.url, coalesce(nullif(i.description, ''), p.description),
          i.posted_at, i.workplace_type)
  ),
  saved as (
    insert into public.postings as p (source, board, external_id, title, company, location, url, description, posted_at, workplace_type)
    select i.source, i.board, i.external_id, i.title, i.company, i.location, i.url, coalesce(i.description, ''), i.posted_at, i.workplace_type
    from incoming i
    where not exists (select 1 from unchanged u where u.source = i.source and u.external_id = i.external_id)
    on conflict (source, external_id) do update set
      board = excluded.board,
      title = excluded.title,
      company = excluded.company,
      location = excluded.location,
      url = excluded.url,
      description = coalesce(nullif(excluded.description, ''), p.description),
      posted_at = excluded.posted_at,
      workplace_type = excluded.workplace_type,
      closed_at = null
    returning p.id, p.source, p.external_id, p.created_at
  )
  select * from saved
  union all
  select * from unchanged;
$$;
