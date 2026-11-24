-- The saved-jobs size and open jobs without an embedding, for admins only. Runs in a transaction that is rolled back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(3);

insert into postings (source, board, external_id, title, company, url) values
  ('lever', 'acme', 'bare-1', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/bare-1');
select set_config('request.jwt.claims', '{"app_metadata":{"role":"admin"}}', true);

select is(
  (admin_storage() ->> 'unembedded')::int,
  (select unembedded::int from storage_totals()),
  'an admin gets the count of open jobs without an embedding'
);
select ok((admin_storage() ->> 'bytes')::bigint > 0, 'an admin gets the space saved jobs take');

select set_config('request.jwt.claims', '{"app_metadata":{}}', true);
select throws_ok('select public.admin_storage()', '42501', 'Only admins can do this.', 'anyone else is refused');

select * from finish();
rollback;
