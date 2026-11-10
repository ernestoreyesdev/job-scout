-- Recent job lists for boards whose systems leave descriptions out of them (Workday and the like), so searches
-- within a few hours reuse them instead of paging through the board again. Descriptions are fetched per job only
-- for jobs being scored. RLS is on with no policies, so only the service role (the agent) can read or write them.
create table public.board_snapshots (
  source text not null,
  board text not null,
  postings jsonb not null,
  fetched_at timestamptz not null default now(),
  primary key (source, board)
);

create index board_snapshots_fetched_at on public.board_snapshots (fetched_at);

alter table public.board_snapshots enable row level security;
