-- Latest step of a run in plain words, shown while the run works.
alter table public.agent_runs add column progress text;
