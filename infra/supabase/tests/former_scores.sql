-- Deleting a tracked job keeps its score and label in former_scores without the user; an unscored, unrated job leaves
-- nothing. Runs in a transaction that is rolled back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(4);

insert into auth.users (id, email) values ('00000000-0000-0000-0000-0000000000e1', 'rater@example.com');
insert into postings (source, board, external_id, title, company, url) values
  ('lever', 'acme', 'kept-1', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/kept-1'),
  ('lever', 'acme', 'kept-2', 'Engineer II', 'Acme', 'https://jobs.lever.co/acme/kept-2');
insert into applications (user_id, posting_id, fit_score, fit_label, score_model, score_prompt_version)
select '00000000-0000-0000-0000-0000000000e1', p.id, s.score, s.label, 'haiku', 'v1'
from (values ('kept-1', 30, 'bad'), ('kept-2', null, null)) as s (job, score, label)
join postings p on p.source = 'lever' and p.external_id = s.job;

set local role authenticated;
select set_config('request.jwt.claims', '{"sub": "00000000-0000-0000-0000-0000000000e1", "role": "authenticated"}', true);
delete from applications;
select is((select count(*)::int from applications), 0, 'the user deletes their tracked jobs');
reset role;

select is(
  (select jsonb_agg(jsonb_build_array(f.fit_score, f.fit_label, f.score_model)) from former_scores f
   join postings p on p.id = f.posting_id where p.external_id = 'kept-1'),
  '[[30, "bad", "haiku"]]'::jsonb,
  'a scored, rated job keeps its score and label'
);
select is(
  (select count(*)::int from former_scores f join postings p on p.id = f.posting_id where p.external_id = 'kept-2'),
  0,
  'an unscored, unrated job leaves nothing'
);
select hasnt_column('former_scores', 'user_id', 'the copy has no user');

select * from finish();
rollback;
