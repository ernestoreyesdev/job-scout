-- At most one unfinished search per user; a second one is refused at insert.
create unique index agent_runs_one_active_per_user on public.agent_runs (user_id)
  where status in ('queued', 'running');

-- Consecutive searches that found the board gone; the agent removes the company at 3.
alter table public.companies add column missed_checks integer not null default 0;
