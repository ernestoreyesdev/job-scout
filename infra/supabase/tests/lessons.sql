-- Each user reads and writes only their own lessons, and deleting the account deletes them. Runs in a transaction
-- that is rolled back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(4);

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000f1', 'learner@example.com'),
  ('00000000-0000-0000-0000-0000000000f2', 'other@example.com');
insert into lessons (user_id, text, source) values
  ('00000000-0000-0000-0000-0000000000f1', 'Prefers remote roles', 'learned'),
  ('00000000-0000-0000-0000-0000000000f2', 'No clearance jobs', 'user');

set local role authenticated;
select set_config('request.jwt.claims', '{"sub": "00000000-0000-0000-0000-0000000000f1", "role": "authenticated"}', true);
select is((select array_agg(text) from lessons), array['Prefers remote roles'], 'a user reads only their own lessons');
select throws_ok(
  $$insert into lessons (user_id, text, source) values ('00000000-0000-0000-0000-0000000000f2', 'Planted', 'user')$$,
  '42501',
  null,
  'a user can''t add a lesson for someone else'
);
update lessons set deleted_at = now() where user_id = '00000000-0000-0000-0000-0000000000f2';
reset role;

select is(
  (select deleted_at from lessons where user_id = '00000000-0000-0000-0000-0000000000f2'),
  null,
  'a user can''t delete someone else''s lesson'
);

select delete_account('00000000-0000-0000-0000-0000000000f1');
select is(
  (select count(*)::int from lessons where user_id = '00000000-0000-0000-0000-0000000000f1'),
  0,
  'deleting the account deletes its lessons'
);

select * from finish();
rollback;
