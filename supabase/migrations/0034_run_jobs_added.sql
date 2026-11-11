-- How many jobs a finished search added to the Tracker. Earlier searches get it from their summary.
alter table public.agent_runs add column jobs_added integer;

update public.agent_runs
set jobs_added = coalesce(
  substring(progress from '^Added (?:your |the )?(\d+)'),
  substring(progress from 'kept the top (\d+)'),
  substring(progress from '^Scored and saved (\d+)'),
  '0'
)::integer
where kind = 'search' and status = 'done';
