-- delete_account() on a user with a resume, scored jobs, a run and a session, and on an admin. Runs in a
-- transaction that is rolled back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(10);

insert into auth.users (id, email) values ('00000000-0000-0000-0000-0000000000b1', 'leaving@example.com');
insert into auth.users (id, email, raw_app_meta_data)
values ('00000000-0000-0000-0000-0000000000b2', 'admin@example.com', '{"role": "admin"}');
insert into auth.sessions (id, user_id) values ('00000000-0000-0000-0000-0000000000c1', '00000000-0000-0000-0000-0000000000b1');
insert into postings (source, board, external_id, title, company, url) values
  ('lever', 'acme', 'leave-1', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/leave-1'),
  ('lever', 'acme', 'leave-2', 'Engineer II', 'Acme', 'https://jobs.lever.co/acme/leave-2'),
  ('lever', 'acme', 'leave-3', 'Engineer III', 'Acme', 'https://jobs.lever.co/acme/leave-3');
insert into resumes (user_id, storage_path, file_name)
values ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000b1/cv.pdf', 'cv.pdf');
insert into applications (user_id, posting_id, fit_score, fit_label, score_model, score_prompt_version)
select '00000000-0000-0000-0000-0000000000b1', p.id, s.score, s.label, 'haiku', 'v1'
from (values ('leave-1', 80, 'good'), ('leave-2', 40, null), ('leave-3', null, null)) as s (job, score, label)
join postings p on p.source = 'lever' and p.external_id = s.job;
insert into agent_runs (id, user_id, kind, status)
values ('00000000-0000-0000-0000-0000000000d1', '00000000-0000-0000-0000-0000000000b1', 'search', 'done');
delete from account_deletions;

select delete_account('00000000-0000-0000-0000-0000000000b1');

select is((select count(*)::int from auth.users where id = '00000000-0000-0000-0000-0000000000b1'), 0, 'the account is gone');
select is((select count(*)::int from auth.sessions where id = '00000000-0000-0000-0000-0000000000c1'), 0, 'its sessions go with it');
select is((select count(*)::int from resumes where user_id = '00000000-0000-0000-0000-0000000000b1'), 0, 'its resumes are deleted');
select is((select count(*)::int from applications where user_id = '00000000-0000-0000-0000-0000000000b1'), 0, 'its tracked jobs are deleted');
select is(
  (select user_id from agent_runs where id = '00000000-0000-0000-0000-0000000000d1'),
  null,
  'its runs stay, with no user'
);
select is(
  (select jsonb_agg(jsonb_build_array(f.fit_score, f.fit_label, f.score_model) order by f.fit_score desc) from former_scores f
   join postings p on p.id = f.posting_id where p.external_id in ('leave-1', 'leave-2', 'leave-3')),
  '[[80, "good", "haiku"], [40, null, "haiku"]]'::jsonb,
  'its scores and labels move to former_scores, unscored jobs do not'
);
select is((select count(*)::int from account_deletions), 1, 'the deletion is counted');

select delete_account('00000000-0000-0000-0000-0000000000b1');
select is((select count(*)::int from account_deletions), 1, 'deleting a missing account counts nothing');

select throws_ok(
  $$select delete_account('00000000-0000-0000-0000-0000000000b2')$$,
  '42501',
  'Admin accounts can''t be deleted.',
  'an admin account is refused'
);

set local role authenticated;
select throws_ok(
  $$select public.delete_account('00000000-0000-0000-0000-0000000000b2')$$,
  '42501',
  null,
  'signed-in users can''t call it'
);
reset role;

select * from finish();
rollback;
