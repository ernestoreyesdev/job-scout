-- Each user reads and writes only their own marked searches, and deleting the account deletes them. Runs in a
-- transaction that is rolled back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(5);

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000e1', 'searcher@example.com'),
  ('00000000-0000-0000-0000-0000000000e2', 'other@example.com');
insert into search_alerts (user_id, rule) values
  ('00000000-0000-0000-0000-0000000000e1', '{"keywords": ["backend engineer"]}'),
  ('00000000-0000-0000-0000-0000000000e2', '{"keywords": ["designer"]}');

set local role authenticated;
select set_config('request.jwt.claims', '{"sub": "00000000-0000-0000-0000-0000000000e1", "role": "authenticated"}', true);
select is(
  (select array_agg(rule ->> 'keywords') from search_alerts),
  array['["backend engineer"]'],
  'a user reads only their own marked searches'
);
select throws_ok(
  $$insert into search_alerts (user_id, rule) values ('00000000-0000-0000-0000-0000000000e2', '{"keywords": ["planted"]}')$$,
  '42501',
  null,
  'a user can''t mark a search for someone else'
);
select throws_ok(
  $$insert into search_alerts (user_id, rule) values ('00000000-0000-0000-0000-0000000000e1', '{"keywords": ["backend engineer"]}')$$,
  '23505',
  null,
  'the same search can''t be marked twice'
);
delete from search_alerts where user_id = '00000000-0000-0000-0000-0000000000e2';
reset role;

select is(
  (select count(*)::int from search_alerts where user_id = '00000000-0000-0000-0000-0000000000e2'),
  1,
  'a user can''t unmark someone else''s search'
);

select delete_account('00000000-0000-0000-0000-0000000000e1');
select is(
  (select count(*)::int from search_alerts where user_id = '00000000-0000-0000-0000-0000000000e1'),
  0,
  'deleting the account deletes its marked searches'
);

select * from finish();
rollback;
