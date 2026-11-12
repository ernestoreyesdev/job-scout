-- Boards ("source/board") a search couldn't reach after a retry, for the admin's health view.
alter table public.agent_runs add column unreachable_boards text[] not null default '{}';
