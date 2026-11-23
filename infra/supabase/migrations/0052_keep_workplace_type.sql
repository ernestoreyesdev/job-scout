-- Saving jobs keeps a job's saved workplace type when its board lists none, so one found while scoring stays.
-- Same inputs and outputs as before.
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
      and (p.board, p.title, p.company, p.location, p.url, p.description_hash, p.posted_at, p.workplace_type)
        is not distinct from (i.board, i.title, i.company, i.location, i.url, coalesce(i.description_hash, p.description_hash),
          i.posted_at, coalesce(i.workplace_type, p.workplace_type))
  ),
  rewritten as (
    delete from public.posting_embeddings e
    using incoming i
    join public.postings p on p.source = i.source and p.external_id = i.external_id
    where e.posting_id = p.id and i.description_hash is not null and i.description_hash is distinct from p.description_hash
  ),
  saved as (
    insert into public.postings as p (source, board, external_id, title, company, location, url, description_hash, posted_at, workplace_type)
    select i.source, i.board, i.external_id, i.title, i.company, i.location, i.url, i.description_hash, i.posted_at, i.workplace_type
    from incoming i
    where not exists (select 1 from unchanged u where u.source = i.source and u.external_id = i.external_id)
    on conflict (source, external_id) do update set
      board = excluded.board,
      title = excluded.title,
      company = excluded.company,
      location = excluded.location,
      url = excluded.url,
      description = case
        when excluded.description_hash is not null and excluded.description_hash is distinct from p.description_hash then ''
        else p.description
      end,
      description_hash = coalesce(excluded.description_hash, p.description_hash),
      posted_at = excluded.posted_at,
      workplace_type = coalesce(excluded.workplace_type, p.workplace_type),
      closed_at = null
    returning p.id, p.source, p.external_id, p.created_at
  )
  select * from saved
  union all
  select * from unchanged;
$$;
