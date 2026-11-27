-- Turns the resume sections into vectors once, then scores each job by its closest section.
create or replace function public.rank_postings(job_ids uuid[], sections jsonb)
returns table (id uuid, similarity double precision)
language sql
stable
set search_path = public, extensions
as $$
  with vectors as materialized (
    select (s.value::text)::extensions.vector as embedding from jsonb_array_elements(sections) s
  )
  select e.posting_id, max(1 - (e.embedding <=> v.embedding)) as similarity
  from public.posting_embeddings e
  cross join vectors v
  where e.posting_id = any(job_ids)
  group by e.posting_id
  order by similarity desc;
$$;
