-- Job embeddings (FastEmbed bge-small-en-v1.5, 384 dimensions), so scoring can show the user's labeled jobs nearest
-- the jobs being scored. Filled by the agent for jobs it scores and jobs the user labels.
create extension if not exists vector with schema extensions;

alter table public.postings add column embedding extensions.vector(384);

-- Writes many embeddings in one call; only the service role (the agent) can run it.
create function public.set_posting_embeddings(embeddings jsonb)
returns void
language sql
set search_path = public, extensions
as $$
  update public.postings p
  set embedding = (e ->> 'embedding')::extensions.vector
  from jsonb_array_elements(embeddings) e
  where p.id = (e ->> 'id')::uuid;
$$;

revoke execute on function public.set_posting_embeddings(jsonb) from public, anon, authenticated;

-- The caller's good and bad jobs nearest the average embedding of job_ids, up to per_label of each, nearest first.
-- Runs with the caller's rights, so RLS limits it to their own labels.
create function public.nearest_labeled_jobs(job_ids uuid[], per_label integer)
returns table (fit_label text, posting jsonb)
language sql
stable
set search_path = public, extensions
as $$
  with anchor as (
    select avg(embedding) as embedding from public.postings where id = any(job_ids) and embedding is not null
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
      row_number() over (partition by a.fit_label order by p.embedding <=> anchor.embedding) as rank
    from public.applications a
    join public.postings p on p.id = a.posting_id
    cross join anchor
    where a.fit_label is not null and p.embedding is not null
  )
  select fit_label, posting from ranked where rank <= per_label order by fit_label desc, rank;
$$;
