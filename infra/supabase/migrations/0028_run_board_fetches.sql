-- How long each board took to fetch in a search, with its job count and outcome (ok, gone or unreachable).
alter table public.agent_runs add column board_fetches jsonb not null default '[]';
