-- The admin page's figures from admin_stats(), each section on its own sample rows. Runs in a transaction that is
-- rolled back, so the deletes below only clear the tables for these checks.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(28);

insert into auth.users (id, email) values ('00000000-0000-0000-0000-0000000000a1', 'admin@example.com');
select set_config('request.jwt.claims', '{"app_metadata":{"role":"admin"}}', true);

create temporary table this_week as
  select date_trunc('week', now() at time zone 'UTC') at time zone 'UTC' as monday;

-- Claude calls summed up by step.
delete from llm_calls;
insert into llm_calls (user_id, step, model, duration_ms, input_tokens, output_tokens, cache_read_input_tokens, error)
select '00000000-0000-0000-0000-0000000000a1', step, 'haiku', ms, 100, 10, 50, error
from (values ('scoring', 900, null), ('scoring', 1200, null), ('scoring', 3000, 'overloaded'), ('titles', 400, null)) as c (step, ms, error);

select is(admin_stats() -> 'calls' -> 0 ->> 'step', 'scoring', 'the busiest step comes first');
select is(
  (select jsonb_build_array(s -> 'calls', s -> 'errors', s -> 'median_ms', s -> 'p95_ms') from jsonb_array_elements(admin_stats() -> 'calls') s where s ->> 'step' = 'scoring'),
  '[3, 1, 1200, 3000]'::jsonb,
  'a step counts its calls and errors, with the median and slowest 5% time'
);
select is(
  (select jsonb_build_array(s -> 'input_tokens', s -> 'cache_read_input_tokens') from jsonb_array_elements(admin_stats() -> 'calls') s where s ->> 'step' = 'scoring'),
  '[300, 150]'::jsonb,
  'a step sums its tokens'
);
select is(
  (select jsonb_build_array(s -> 'calls', s -> 'median_ms') from jsonb_array_elements(admin_stats() -> 'calls') s where s ->> 'step' = 'titles'),
  '[1, 400]'::jsonb,
  'a single call is its own median'
);

-- Page speed by page and metric.
delete from web_vitals;
insert into web_vitals (user_id, page, metric, value)
select '00000000-0000-0000-0000-0000000000a1', page, metric, value
from (values ('Tracker', 'LCP', 800), ('Tracker', 'LCP', 1200), ('Tracker', 'LCP', 2000), ('Tracker', 'LCP', 3500), ('Tracker', 'TTFB', 300), ('Jobs', 'LCP', 900))
  as v (page, metric, value);

select is(
  (select jsonb_build_array(v -> 'count', v -> 'median', v -> 'p75') from jsonb_array_elements(admin_stats() -> 'vitals') v where v ->> 'page' = 'Tracker' and v ->> 'metric' = 'LCP'),
  '[4, 2000, 3500]'::jsonb,
  'a metric gives its count, median and 75th percentile'
);
select is(admin_stats() -> 'vitals' -> 0 ->> 'page', 'Tracker', 'the most measured page comes first');

-- Board fetches by job system and the slowest boards.
delete from agent_runs;
insert into agent_runs (user_id, kind, status, board_fetches) values (
  '00000000-0000-0000-0000-0000000000a1', 'search', 'done',
  '[{"board": "workday/acme", "source": "workday", "ms": 9000, "jobs": 1800, "outcome": "ok"},
    {"board": "workday/acme", "source": "workday", "ms": 11000, "jobs": 1850, "outcome": "ok"},
    {"board": "lever/beta", "source": "lever", "ms": 400, "jobs": 30, "outcome": "ok"},
    {"board": "lever/gone", "source": "lever", "ms": 200, "jobs": 0, "outcome": "gone"}]'
);

select is(
  (select jsonb_build_array(s -> 'source', s -> 'fetches', s -> 'total_ms', s -> 'jobs') from jsonb_array_elements(admin_stats() -> 'boards' -> 'sources') with ordinality as x (s, n) where n = 1),
  '["workday", 2, 20000, 1850]'::jsonb,
  'the job system with the most fetch time comes first, with its fetches and most jobs'
);
select is(
  (select jsonb_build_array(s -> 'fetches', s -> 'failures') from jsonb_array_elements(admin_stats() -> 'boards' -> 'sources') s where s ->> 'source' = 'lever'),
  '[2, 1]'::jsonb,
  'a fetch that found the board gone counts as failed'
);
select is(
  (select jsonb_agg(b ->> 'board') from jsonb_array_elements(admin_stats() -> 'boards' -> 'slowest') b),
  '["workday/acme", "lever/beta", "lever/gone"]'::jsonb,
  'boards are listed slowest first'
);
select is((admin_stats() -> 'boards' -> 'slowest' -> 0 -> 'median_ms')::int, 11000, 'two fetches take the later one as the median');

-- Refresh fetches joined with the directory.
delete from board_refreshes;
delete from companies;
insert into board_refreshes (started_at, stopped_at, board_fetches) values
  (now() - interval '1 hour', null, '[{"board": "ashby/acme", "ms": 300, "outcome": "ok"}, {"board": "lever/beta", "ms": 900, "outcome": "unreachable"}]'),
  (now() - interval '2 hours', now(), '[{"board": "ashby/acme", "ms": 100, "outcome": "ok"}]');
insert into companies (name, source, board, found_by, open_jobs) values
  ('Acme', 'ashby', 'acme', 'lookup', 10),
  ('New', 'greenhouse', 'new', 'lookup', 0);

select is(
  (select jsonb_agg(b ->> 'board') from jsonb_array_elements(admin_stats() -> 'refresh_boards') b),
  '["lever/beta", "ashby/acme", "greenhouse/new"]'::jsonb,
  'refresh boards are listed slowest first, unfetched ones last'
);
select is(
  (select jsonb_build_array(b -> 'median_ms', b -> 'last_ms', b -> 'failures', b -> 'open_jobs') from jsonb_array_elements(admin_stats() -> 'refresh_boards') b where b ->> 'board' = 'ashby/acme'),
  '[300, 300, 0, 10]'::jsonb,
  'a board gives its median and latest fetch time, failures and open jobs'
);
select is(
  (select jsonb_build_array(b -> 'failures', b -> 'open_jobs') from jsonb_array_elements(admin_stats() -> 'refresh_boards') b where b ->> 'board' = 'lever/beta'),
  '[1, 0]'::jsonb,
  'a fetched board missing from the directory has no open jobs'
);
select is(
  (select jsonb_build_array(b -> 'median_ms', b -> 'open_jobs') from jsonb_array_elements(admin_stats() -> 'refresh_boards') b where b ->> 'board' = 'greenhouse/new'),
  '[null, 0]'::jsonb,
  'a directory board never fetched has no times'
);
select is(
  (select jsonb_agg(r ->> 'stopped_at' is not null) from jsonb_array_elements(admin_stats() -> 'refreshes') r),
  '[false, true]'::jsonb,
  'refreshes are listed newest first, a stopped one with when it was stopped'
);

-- Model quality week by week.
delete from llm_calls;
delete from agent_runs;
delete from applications;
insert into postings (source, board, external_id, title, company, url) values
  ('lever', 'acme', 'job-1', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/job-1'),
  ('lever', 'acme', 'job-2', 'Engineer II', 'Acme', 'https://jobs.lever.co/acme/job-2'),
  ('lever', 'acme', 'job-3', 'Engineer III', 'Acme', 'https://jobs.lever.co/acme/job-3')
on conflict (source, external_id) do nothing;
insert into llm_calls (user_id, step, model, duration_ms, input_tokens, cache_read_input_tokens, error, stop_reason, created_at)
select '00000000-0000-0000-0000-0000000000a1', 'scoring', 'haiku', ms, input, cached, error, stop, (select monday from this_week) + offset_days
from (values
  (100, 20, 80, null, 'end_turn', interval '1 day'),
  (300, 100, 0, 'overloaded', null, interval '2 days'),
  (200, 50, 0, null, 'max_tokens', interval '-6 days')
) as c (ms, input, cached, error, stop, offset_days);
insert into agent_runs (user_id, kind, status, usage, created_at) values
  ('00000000-0000-0000-0000-0000000000a1', 'search', 'done', '{"input_tokens": 1000, "output_tokens": 10}', (select monday from this_week) + interval '1 day');
insert into applications (user_id, posting_id, fit_score, fit_label, created_at, updated_at)
select '00000000-0000-0000-0000-0000000000a1', p.id, s.score, s.label, (select monday from this_week) + interval '1 day', (select monday from this_week) + interval '1 day'
from (values ('job-1', 80, 'good'), ('job-2', 40, null)) as s (job, score, label)
join postings p on p.source = 'lever' and p.external_id = s.job;

select is(jsonb_array_length(admin_stats() -> 'model_weeks'), 2, 'calls fall into the week they were made');
select is(
  (select jsonb_build_array(w -> 'calls', w -> 'broken') from jsonb_array_elements(admin_stats() -> 'model_weeks') with ordinality as x (w, n) where n = 1),
  '[1, 1]'::jsonb,
  'the earlier week comes first and counts a cut-off answer as broken'
);
select is(
  (select jsonb_build_array(w -> 'calls', w -> 'errors', w -> 'broken', w -> 'median_ms', w -> 'cache_share') from jsonb_array_elements(admin_stats() -> 'model_weeks') with ordinality as x (w, n) where n = 2),
  '[2, 1, 0, 300, 0.4]'::jsonb,
  'a week counts calls and errors, with the median time and the share of input read from cache'
);
select is(
  (select jsonb_build_array(w -> 'searches', w -> 'search_usage' -> 'input_tokens') from jsonb_array_elements(admin_stats() -> 'model_weeks') with ordinality as x (w, n) where n = 2),
  '[1, 1000]'::jsonb,
  'a week counts finished searches and sums their usage'
);
select is(
  (select jsonb_build_array(w -> 'scored', w -> 'average_score', w -> 'rated', w -> 'good') from jsonb_array_elements(admin_stats() -> 'model_weeks') with ordinality as x (w, n) where n = 2),
  '[2, 60, 1, 1]'::jsonb,
  'a week averages the scores given and counts the ratings made'
);
select is(
  (select w ->> 'week' from jsonb_array_elements(admin_stats() -> 'model_weeks') with ordinality as x (w, n) where n = 2),
  to_char((select monday from this_week), 'YYYY-MM-DD'),
  'weeks are named by their Monday'
);

-- Prompt versions per step.
delete from llm_calls;
insert into llm_calls (user_id, step, model, duration_ms, prompt_version, created_at) values
  ('00000000-0000-0000-0000-0000000000a1', 'scoring', 'haiku', 100, 'aaaa1111', now() - interval '12 days'),
  ('00000000-0000-0000-0000-0000000000a1', 'scoring', 'haiku', 100, 'aaaa1111', now() - interval '8 days'),
  ('00000000-0000-0000-0000-0000000000a1', 'scoring', 'haiku', 100, 'bbbb2222', now() - interval '4 days');

select is(
  (select jsonb_build_array(v -> 'prompt_version', v -> 'calls') from jsonb_array_elements(admin_stats() -> 'prompt_versions') with ordinality as x (v, n) where n = 1),
  '["bbbb2222", 1]'::jsonb,
  'the most recently used version comes first'
);
select is(
  (select (v ->> 'calls')::int from jsonb_array_elements(admin_stats() -> 'prompt_versions') with ordinality as x (v, n) where n = 2),
  2,
  'an older version counts all its calls'
);
select ok(
  (select (v ->> 'first')::timestamptz < (v ->> 'last')::timestamptz from jsonb_array_elements(admin_stats() -> 'prompt_versions') with ordinality as x (v, n) where n = 2),
  'a version gives when it was first and last used'
);

-- Fit scores per version, checked against ratings.
delete from applications;
insert into applications (user_id, posting_id, fit_score, fit_label, score_prompt_version, score_model)
select '00000000-0000-0000-0000-0000000000a1', p.id, s.score, s.label, 'v1', 'haiku'
from (values ('job-1', 85, 'good'), ('job-2', 75, 'bad'), ('job-3', 30, null)) as s (job, score, label)
join postings p on p.source = 'lever' and p.external_id = s.job;

select is(
  (select jsonb_build_array(v -> 'scored', v -> 'rated', v -> 'good', v -> 'predicted_good', v -> 'predicted_good_correct') from jsonb_array_elements(admin_stats() -> 'score_versions') v),
  '[3, 2, 1, 2, 1]'::jsonb,
  'a version counts its scores and ratings, and how many it predicted good correctly'
);
select is(
  round((admin_stats() -> 'score_versions' -> 0 ->> 'average_score')::numeric, 2),
  63.33,
  'a version averages its scores'
);

-- Only admins.
select set_config('request.jwt.claims', '{"app_metadata":{}}', true);
select throws_ok('select public.admin_stats()', '42501', 'Only admins can do this.', 'anyone else is refused');
select set_config('request.jwt.claims', '{"app_metadata":{"role":"admin"}}', true);
select ok(admin_stats() ? 'storage', 'an admin gets the storage totals too');

select * from finish();
rollback;
