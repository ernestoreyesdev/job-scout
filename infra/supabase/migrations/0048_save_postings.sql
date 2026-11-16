-- Saves fetched jobs, writing only the ones that are new, changed or listed again after closing, and returns every
-- job's id. A job sent without a description keeps the saved one. Only the service role (the agent) can run it.
create function public.save_postings(jobs jsonb)
returns table (id uuid, source public.job_source, external_id text, created_at timestamptz)
language sql
set search_path = public
as $$
  with incoming as (
    select * from jsonb_populate_recordset(null::public.postings, jobs)
  ),
  saved as (
    insert into public.postings as p (source, board, external_id, title, company, location, url, description, posted_at, workplace_type)
    select i.source, i.board, i.external_id, i.title, i.company, i.location, i.url, coalesce(i.description, ''), i.posted_at, i.workplace_type
    from incoming i
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
    where (p.board, p.title, p.company, p.location, p.url, p.description, p.posted_at, p.workplace_type, p.closed_at)
      is distinct from (excluded.board, excluded.title, excluded.company, excluded.location, excluded.url,
        coalesce(nullif(excluded.description, ''), p.description), excluded.posted_at, excluded.workplace_type, null::timestamptz)
    returning p.id, p.source, p.external_id, p.created_at
  )
  select * from saved
  union all
  select p.id, p.source, p.external_id, p.created_at
  from public.postings p
  join incoming i on i.source = p.source and i.external_id = p.external_id
  where p.id not in (select saved.id from saved);
$$;

-- Closes a board's open jobs that aren't in listed, and returns how many it closed.
create function public.close_unlisted_postings(job_source public.job_source, job_board text, listed text[])
returns integer
language sql
set search_path = public
as $$
  with closed as (
    update public.postings set closed_at = now()
    where source = job_source and board = job_board and closed_at is null and external_id <> all (listed)
    returning 1
  )
  select count(*)::integer from closed;
$$;

revoke execute on function public.save_postings(jsonb) from public, anon, authenticated;
revoke execute on function public.close_unlisted_postings(public.job_source, text, text[]) from public, anon, authenticated;

alter table public.postings drop column last_seen_at;
