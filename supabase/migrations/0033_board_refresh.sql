-- Every job on every directory board lives in postings, refreshed daily and on searches that find a board stale.
-- last_seen_at is when a fetch last listed the job; a complete fetch closes the board's jobs it no longer lists.
alter table public.postings add column last_seen_at timestamptz;

create index postings_board on public.postings (source, board);

-- One row per daily refresh, with each board's fetch. RLS is on with no policies, so only the agent can use it.
create table public.board_refreshes (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  boards integer not null default 0,
  jobs integer not null default 0,
  new_jobs integer not null default 0,
  closed_jobs integer not null default 0,
  deleted_jobs integer not null default 0,
  failures integer not null default 0,
  board_fetches jsonb not null default '[]'
);

create index board_refreshes_started_at on public.board_refreshes (started_at desc);

alter table public.board_refreshes enable row level security;

-- Deletes jobs closed more than `days` ago that no user tracks; returns how many. Only the agent can run it.
create function public.delete_stale_postings(days integer)
returns integer
language sql
as $$
  with deleted as (
    delete from public.postings p
    where p.closed_at < now() - make_interval(days => days)
      and not exists (select 1 from public.applications a where a.posting_id = p.id)
    returning 1
  )
  select count(*)::integer from deleted;
$$;

revoke execute on function public.delete_stale_postings(integer) from public, anon, authenticated;

-- Jobs and storage per board, for the admin page. Only the agent can run it.
create function public.board_storage()
returns table (source text, board text, jobs bigint, open_jobs bigint, bytes bigint)
language sql
stable
as $$
  select
    p.source::text,
    p.board,
    count(*),
    count(*) filter (where p.closed_at is null),
    sum(pg_column_size(p.*))::bigint
  from public.postings p
  where p.source <> 'hackernews'
  group by p.source, p.board;
$$;

revoke execute on function public.board_storage() from public, anon, authenticated;

drop table public.board_snapshots;
