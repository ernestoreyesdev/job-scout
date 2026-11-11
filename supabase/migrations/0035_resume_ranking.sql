-- Ranks jobs by how close each is to the nearest section of a resume, so searches pick what to score without Claude.
alter table public.board_refreshes add column embedded_jobs integer not null default 0;

-- job_ids' postings that have an embedding, most similar first; `sections` is a JSON array of resume section embeddings.
create function public.rank_postings(job_ids uuid[], sections jsonb)
returns table (id uuid, similarity double precision)
language sql
stable
set search_path = public, extensions
as $$
  select p.id, max(1 - (p.embedding <=> (s.value::text)::extensions.vector)) as similarity
  from public.postings p
  cross join jsonb_array_elements(sections) s
  where p.id = any(job_ids) and p.embedding is not null
  group by p.id
  order by similarity desc;
$$;

revoke execute on function public.rank_postings(uuid[], jsonb) from public, anon, authenticated;

-- Jobs, embedded open jobs and storage per board, for the admin page. Only the agent can run it.
drop function public.board_storage();

create function public.board_storage()
returns table (source text, board text, jobs bigint, open_jobs bigint, embedded bigint, bytes bigint)
language sql
stable
as $$
  select
    p.source::text,
    p.board,
    count(*),
    count(*) filter (where p.closed_at is null),
    count(*) filter (where p.closed_at is null and p.embedding is not null),
    sum(pg_column_size(p.*))::bigint
  from public.postings p
  where p.source <> 'hackernews'
  group by p.source, p.board;
$$;

revoke execute on function public.board_storage() from public, anon, authenticated;
