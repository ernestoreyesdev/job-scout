-- A job title compared without case, punctuation or extra spaces: "Sr. Engineer - Remote" is "sr engineer remote".
create function public.title_key(title text)
returns text
language sql
immutable
as $$
  select lower(trim(regexp_replace(title, '[^a-zA-Z0-9]+', ' ', 'g')));
$$;

create index postings_company_title on public.postings (company, public.title_key(title));

-- Which of job_ids are reposts: the same company had a job with the same title that started earlier and has since
-- closed, or that started at least `days` days earlier. Jobs listed side by side, like one title in several cities, aren't.
create function public.reposted_postings(job_ids uuid[], days integer)
returns table (id uuid)
language sql
stable
as $$
  select p.id
  from public.postings p
  where p.id = any(job_ids)
    and exists (
      select 1
      from public.postings o
      where o.company = p.company
        and public.title_key(o.title) = public.title_key(p.title)
        and o.id <> p.id
        and o.created_at < p.created_at
        and (o.closed_at is not null or o.created_at <= p.created_at - make_interval(days => days))
    );
$$;
