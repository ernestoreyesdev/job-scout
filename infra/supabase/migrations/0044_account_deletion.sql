-- Deleting an account removes everything personal and keeps the stats: Claude calls and page loads carry no user,
-- a deleted user's runs stay without one, their scores and labels move to former_scores and the deletion itself is
-- counted in account_deletions. Admin accounts can't be deleted.
alter table public.llm_calls drop column user_id;

drop policy "add own web vitals" on public.web_vitals;
alter table public.web_vitals drop column user_id;
create policy "add web vitals" on public.web_vitals for insert to authenticated with check (true);

alter table public.agent_runs alter column user_id drop not null;
alter table public.agent_runs drop constraint agent_runs_user_id_fkey;
alter table public.agent_runs
  add constraint agent_runs_user_id_fkey foreign key (user_id) references auth.users (id) on delete set null;

-- Scores and labels from deleted accounts. RLS is on with no policies, so only the service role can use it.
create table public.former_scores (
  id uuid primary key default gen_random_uuid(),
  posting_id uuid references public.postings (id) on delete set null,
  fit_score integer,
  fit_label text,
  score_model text,
  score_prompt_version text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

alter table public.former_scores enable row level security;

-- One row per deleted account, with only the date. RLS is on with no policies, so only the service role can use it.
create table public.account_deletions (
  id uuid primary key default gen_random_uuid(),
  deleted_at timestamptz not null default now()
);

alter table public.account_deletions enable row level security;

-- Moves the account's scores and labels to former_scores, deletes the account with everything that cascades from it
-- and counts the deletion, all or nothing. Refuses admin accounts. Only the agent can run it.
create function public.delete_account(target uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (select 1 from auth.users u where u.id = target and u.raw_app_meta_data ->> 'role' = 'admin') then
    raise exception 'Admin accounts can''t be deleted.' using errcode = '42501';
  end if;
  insert into public.former_scores (posting_id, fit_score, fit_label, score_model, score_prompt_version, created_at, updated_at)
  select a.posting_id, a.fit_score, a.fit_label, a.score_model, a.score_prompt_version, a.created_at, a.updated_at
  from public.applications a
  where a.user_id = target and (a.fit_score is not null or a.fit_label is not null);
  delete from auth.users u where u.id = target;
  if found then
    insert into public.account_deletions default values;
  end if;
end;
$$;

revoke execute on function public.delete_account(uuid) from public, anon, authenticated;

create or replace function public.admin_stats()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  since timestamptz := now() - interval '30 days';
  model_since timestamptz := now() - interval '12 weeks';
begin
  if coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') <> 'admin' then
    raise exception 'Only admins can do this.' using errcode = '42501';
  end if;

  return jsonb_build_object(
    'generated_at', now(),
    'days', 30,
    'max_missed_checks', 3,
    'key_hint', (select c.hint from public.shared_credentials c where c.provider = 'anthropic'),
    'users', jsonb_build_object(
      'total', (select count(*) from auth.users),
      'active', (select count(distinct r.user_id) from public.agent_runs r where r.created_at >= now() - interval '7 days'),
      'new_this_month', (select count(*) from auth.users u where u.created_at >= date_trunc('month', now())),
      'deleted', (select count(*) from public.account_deletions)
    ),
    'runs', (
      select coalesce(jsonb_agg(jsonb_build_object(
        'id', r.id, 'kind', r.kind, 'status', r.status, 'error', r.error,
        'error_code', r.error_code, 'unreachable_boards', r.unreachable_boards, 'created_at', r.created_at,
        'finished_at', r.finished_at, 'usage', r.usage, 'timings', r.timings,
        'run_error', case when e.run_id is null then null else jsonb_build_object('detail', e.detail) end
      ) order by r.created_at desc), '[]')
      from public.agent_runs r
      left join public.run_errors e on e.run_id = r.id
      where r.created_at >= since
    ),
    'calls', (
      select coalesce(jsonb_agg(to_jsonb(s) order by s.calls desc, s.step), '[]')
      from (
        select
          l.step,
          count(*) as calls,
          count(*) filter (where coalesce(l.error, '') <> '') as errors,
          (array_agg(l.duration_ms order by l.duration_ms))[floor(count(*) * 0.5)::int + 1] as median_ms,
          (array_agg(l.duration_ms order by l.duration_ms))[floor(count(*) * 0.95)::int + 1] as p95_ms,
          sum(l.input_tokens) as input_tokens,
          sum(l.output_tokens) as output_tokens,
          sum(l.cache_read_input_tokens) as cache_read_input_tokens,
          sum(l.cache_creation_input_tokens) as cache_creation_input_tokens,
          sum(l.web_search_requests) as web_search_requests
        from public.llm_calls l
        where l.created_at >= since
        group by l.step
      ) s
    ),
    'vitals', (
      select coalesce(jsonb_agg(jsonb_build_object(
        'page', v.page, 'metric', v.metric, 'count', v.count, 'median', v.median, 'p75', v.p75
      ) order by v.loads desc, v.page, v.metric), '[]')
      from (
        select
          w.page,
          w.metric,
          count(*) as count,
          (array_agg(w.value order by w.value))[floor(count(*) * 0.5)::int + 1] as median,
          (array_agg(w.value order by w.value))[floor(count(*) * 0.75)::int + 1] as p75,
          max(count(*)) over (partition by w.page) as loads
        from public.web_vitals w
        where w.created_at >= since
        group by w.page, w.metric
      ) v
    ),
    'boards', (
      with fetches as (
        select
          f ->> 'source' as source,
          f ->> 'board' as board,
          (f ->> 'ms')::numeric as ms,
          (f ->> 'jobs')::int as jobs,
          f ->> 'outcome' as outcome
        from public.agent_runs r
        cross join lateral jsonb_array_elements(coalesce(r.board_fetches, '[]')) f
        where r.kind = 'search' and r.created_at >= since
      )
      select jsonb_build_object(
        'sources', (
          select coalesce(jsonb_agg(to_jsonb(s) order by s.total_ms desc), '[]')
          from (
            select
              source,
              count(*) as fetches,
              count(*) filter (where outcome not in ('ok', 'cached')) as failures,
              count(*) filter (where outcome = 'cached') as cached,
              (array_agg(ms order by ms))[floor(count(*) * 0.5)::int + 1] as median_ms,
              max(ms) as max_ms,
              max(jobs) as jobs,
              sum(ms) as total_ms
            from fetches
            group by source
          ) s
        ),
        'slowest', (
          select coalesce(jsonb_agg(to_jsonb(b) order by b.median_ms desc), '[]')
          from (
            select
              board,
              min(source) as source,
              count(*) as fetches,
              count(*) filter (where outcome not in ('ok', 'cached')) as failures,
              count(*) filter (where outcome = 'cached') as cached,
              (array_agg(ms order by ms))[floor(count(*) * 0.5)::int + 1] as median_ms,
              max(ms) as max_ms,
              max(jobs) as jobs
            from fetches
            group by board
            order by median_ms desc
            limit 15
          ) b
        )
      )
    ),
    'model_weeks', (
      with calls as (
        select to_char(date_trunc('week', l.created_at at time zone 'UTC'), 'YYYY-MM-DD') as week, l.*
        from public.llm_calls l
        where l.created_at >= model_since
      ),
      scores as (
        select a.fit_score, a.fit_label, a.created_at, a.updated_at
        from (
          select x.fit_score, x.fit_label, x.score_model, x.score_prompt_version, x.created_at, x.updated_at
          from public.applications x
          union all
          select f.fit_score, f.fit_label, f.score_model, f.score_prompt_version, f.created_at, f.updated_at
          from public.former_scores f
        ) a
        where a.fit_score is not null and a.created_at >= model_since
      ),
      searches as (
        select to_char(date_trunc('week', r.created_at at time zone 'UTC'), 'YYYY-MM-DD') as week, r.usage
        from public.agent_runs r
        where r.kind = 'search' and r.status = 'done' and r.created_at >= model_since
      ),
      call_weeks as (
        select
          week,
          count(*) as calls,
          count(*) filter (where coalesce(error, '') <> '') as errors,
          count(*) filter (where stop_reason in ('max_tokens', 'refusal')) as broken,
          (array_agg(duration_ms order by duration_ms))[floor(count(*) * 0.5)::int + 1] as median_ms,
          sum(input_tokens + cache_read_input_tokens) as input,
          sum(cache_read_input_tokens) as cached
        from calls
        group by week
      ),
      search_weeks as (
        select week, count(*) as searches from searches group by week
      ),
      usage_weeks as (
        select week, jsonb_object_agg(key, total) as usage
        from (
          select s.week, u.key, sum(case when jsonb_typeof(u.value) = 'number' then u.value::numeric else 0 end) as total
          from searches s
          cross join lateral jsonb_each(coalesce(s.usage, '{}')) u
          group by s.week, u.key
        ) t
        group by week
      ),
      score_weeks as (
        select
          to_char(date_trunc('week', created_at at time zone 'UTC'), 'YYYY-MM-DD') as week,
          count(*) as scored,
          avg(fit_score)::float as average_score
        from scores
        group by 1
      ),
      rated_weeks as (
        select
          to_char(date_trunc('week', updated_at at time zone 'UTC'), 'YYYY-MM-DD') as week,
          count(*) as rated,
          count(*) filter (where fit_label = 'good') as good
        from scores
        where fit_label is not null
        group by 1
      ),
      weeks as (
        select week from call_weeks
        union select week from search_weeks
        union select week from score_weeks
        union select week from rated_weeks
      )
      select coalesce(jsonb_agg(jsonb_build_object(
        'week', w.week,
        'calls', coalesce(c.calls, 0),
        'errors', coalesce(c.errors, 0),
        'broken', coalesce(c.broken, 0),
        'median_ms', c.median_ms,
        'cache_share', case when coalesce(c.input, 0) > 0 then c.cached::float / c.input end,
        'searches', coalesce(s.searches, 0),
        'search_usage', coalesce(u.usage, '{}'),
        'scored', coalesce(sc.scored, 0),
        'average_score', sc.average_score,
        'rated', coalesce(ra.rated, 0),
        'good', coalesce(ra.good, 0)
      ) order by w.week), '[]')
      from weeks w
      left join call_weeks c on c.week = w.week
      left join search_weeks s on s.week = w.week
      left join usage_weeks u on u.week = w.week
      left join score_weeks sc on sc.week = w.week
      left join rated_weeks ra on ra.week = w.week
    ),
    'prompt_versions', (
      select coalesce(jsonb_agg(to_jsonb(p) order by p.step desc, p.last desc), '[]')
      from (
        select l.step, l.prompt_version, l.model, count(*) as calls, min(l.created_at) as first, max(l.created_at) as last
        from public.llm_calls l
        where l.created_at >= model_since
        group by l.step, l.prompt_version, l.model
      ) p
    ),
    'score_versions', (
      select coalesce(jsonb_agg(to_jsonb(v) order by v.last desc), '[]')
      from (
        select
          a.score_prompt_version as prompt_version,
          a.score_model as model,
          count(*) as scored,
          avg(a.fit_score)::float as average_score,
          count(*) filter (where a.fit_label is not null) as rated,
          count(*) filter (where a.fit_label = 'good') as good,
          count(*) filter (where a.fit_label is not null and a.fit_score >= 70) as predicted_good,
          count(*) filter (where a.fit_label = 'good' and a.fit_score >= 70) as predicted_good_correct,
          max(a.created_at) as last
        from (
          select x.fit_score, x.fit_label, x.score_model, x.score_prompt_version, x.created_at, x.updated_at
          from public.applications x
          union all
          select f.fit_score, f.fit_label, f.score_model, f.score_prompt_version, f.created_at, f.updated_at
          from public.former_scores f
        ) a
        where a.fit_score is not null and a.created_at >= model_since
        group by a.score_prompt_version, a.score_model
      ) v
    ),
    'evals', (
      select coalesce(jsonb_agg(to_jsonb(e) order by e.created_at desc), '[]')
      from (
        select x.eval, x.model, x.prompt_version, x.metrics, x.cost, x.created_at
        from public.eval_runs x
        order by x.created_at desc
        limit 20
      ) e
    ),
    'refreshes', (
      select coalesce(jsonb_agg(to_jsonb(b) order by b.started_at desc), '[]')
      from (
        select
          x.id, x.started_at, x.finished_at, x.stopped_at, x.boards, x.jobs, x.new_jobs, x.closed_jobs, x.embedded_jobs,
          x.deleted_jobs, x.failures
        from public.board_refreshes x
        where x.started_at >= since
      ) b
    ),
    'refresh_boards', (
      with fetches as (
        select f ->> 'board' as board, (f ->> 'ms')::numeric as ms, f ->> 'outcome' as outcome, b.started_at
        from public.board_refreshes b
        cross join lateral jsonb_array_elements(coalesce(b.board_fetches, '[]')) f
        where b.started_at >= since
      ),
      per_board as (
        select
          board,
          (array_agg(ms order by ms))[floor(count(*) * 0.5)::int + 1] as median_ms,
          (array_agg(ms order by started_at desc))[1] as last_ms,
          (array_agg(outcome order by started_at desc))[1] as last_outcome,
          count(*) filter (where outcome <> 'ok') as failures
        from fetches
        group by board
      ),
      listed as (
        select c.source::text || '/' || c.board as board, c.open_jobs from public.companies c
      )
      select coalesce(jsonb_agg(jsonb_build_object(
        'board', board,
        'source', split_part(board, '/', 1),
        'median_ms', median_ms,
        'last_ms', last_ms,
        'last_outcome', last_outcome,
        'failures', coalesce(failures, 0),
        'open_jobs', coalesce(open_jobs, 0)
      ) order by median_ms desc nulls last), '[]')
      from per_board
      full join listed using (board)
    ),
    'storage', (select jsonb_build_object('bytes', t.bytes, 'unembedded', t.unembedded) from public.storage_totals() t),
    'companies', (
      select coalesce(jsonb_agg(jsonb_build_object(
        'name', c.name, 'source', c.source, 'board', c.board, 'kind', c.kind, 'open_jobs', c.open_jobs,
        'missed_checks', c.missed_checks
      )), '[]')
      from public.companies c
    ),
    'labels', (
      select coalesce(jsonb_agg(jsonb_build_object('fit_score', a.fit_score, 'fit_label', a.fit_label)), '[]')
      from (
        select x.fit_score, x.fit_label, x.score_model, x.score_prompt_version, x.created_at, x.updated_at
        from public.applications x
        union all
        select f.fit_score, f.fit_label, f.score_model, f.score_prompt_version, f.created_at, f.updated_at
        from public.former_scores f
      ) a
      where a.fit_label is not null
    )
  );
end;
$$;
