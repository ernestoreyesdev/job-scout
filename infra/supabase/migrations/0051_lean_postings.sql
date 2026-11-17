-- Keeps each saved job small. Embeddings move to their own table, written once per job. Descriptions stay only on
-- jobs someone tracks, Hacker News and manual jobs; the rest keep a hash of their description to spot changes, and
-- searches fetch a description when they score the job. Jobs from staffing agencies are no longer saved.
create table public.posting_embeddings (
  posting_id uuid primary key references public.postings (id) on delete cascade,
  embedding extensions.vector(384) not null
);

alter table public.posting_embeddings enable row level security;

create policy "signed-in users read posting embeddings" on public.posting_embeddings
  for select to authenticated using (true);

delete from public.postings p
using public.companies c
where c.kind = 'staffing'
  and p.source = c.source
  and p.board = c.board
  and p.id not in (select a.posting_id from public.applications a);

insert into public.posting_embeddings (posting_id, embedding)
select id, embedding from public.postings where embedding is not null;

alter table public.postings add column description_hash text;

update public.postings p
set
  description_hash = case when p.description <> '' then md5(p.description) end,
  description = case
    when p.source in ('hackernews', 'manual') or p.id in (select a.posting_id from public.applications a) then p.description
    else ''
  end;

drop index public.postings_unembedded;
alter table public.postings drop column embedding;

-- Saves fetched jobs, writing only new, changed and reopened ones, and returns every job's id. Jobs come with a
-- description_hash, or none when their list leaves the description out. A changed hash clears the saved description
-- and embedding, so both are made again from the new text.
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
          i.posted_at, i.workplace_type)
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
      workplace_type = excluded.workplace_type,
      closed_at = null
    returning p.id, p.source, p.external_id, p.created_at
  )
  select * from saved
  union all
  select * from unchanged;
$$;

-- Writes many embeddings in one call; only the service role (the agent) can run it.
create or replace function public.set_posting_embeddings(embeddings jsonb)
returns void
language sql
set search_path = public, extensions
as $$
  insert into public.posting_embeddings (posting_id, embedding)
  select (e ->> 'id')::uuid, (e ->> 'embedding')::extensions.vector
  from jsonb_array_elements(embeddings) e
  on conflict (posting_id) do update set embedding = excluded.embedding;
$$;

-- Open jobs without an embedding, newest first, with what the agent embeds them from when it has no fresher text.
create function public.unembedded_postings(max_rows integer)
returns table (id uuid, source public.job_source, external_id text, title text, company text, location text, description text)
language sql
stable
set search_path = public
as $$
  select p.id, p.source, p.external_id, p.title, p.company, p.location, p.description
  from public.postings p
  where p.closed_at is null and not exists (select 1 from public.posting_embeddings e where e.posting_id = p.id)
  order by p.created_at desc
  limit max_rows;
$$;

revoke execute on function public.unembedded_postings(integer) from public, anon, authenticated;

create or replace function public.rank_postings(job_ids uuid[], sections jsonb)
returns table (id uuid, similarity double precision)
language sql
stable
set search_path = public, extensions
as $$
  select e.posting_id, max(1 - (e.embedding <=> (s.value::text)::extensions.vector)) as similarity
  from public.posting_embeddings e
  cross join jsonb_array_elements(sections) s
  where e.posting_id = any(job_ids)
  group by e.posting_id
  order by similarity desc;
$$;

create or replace function public.nearest_labeled_jobs(job_ids uuid[], per_label integer)
returns table (fit_label text, posting jsonb)
language sql
stable
set search_path = public, extensions
as $$
  with anchor as (
    select avg(embedding) as embedding from public.posting_embeddings where posting_id = any(job_ids)
  ),
  ranked as (
    select
      a.fit_label,
      jsonb_build_object(
        'title', p.title,
        'company', p.company,
        'location', p.location,
        'workplace_type', p.workplace_type,
        'years_experience', p.years_experience,
        'tech_stack', p.tech_stack
      ) as posting,
      row_number() over (partition by a.fit_label order by e.embedding <=> anchor.embedding) as rank
    from public.applications a
    join public.postings p on p.id = a.posting_id
    join public.posting_embeddings e on e.posting_id = a.posting_id
    cross join anchor
    where a.fit_label is not null
  )
  select fit_label, posting from ranked where rank <= per_label order by fit_label desc, rank;
$$;

create or replace function public.storage_totals()
returns table (bytes bigint, unembedded bigint)
language sql
stable
as $$
  select
    pg_total_relation_size('public.postings') + pg_total_relation_size('public.posting_embeddings'),
    (
      select count(*) from public.postings p
      where p.closed_at is null and not exists (select 1 from public.posting_embeddings e where e.posting_id = p.id)
    );
$$;
