-- Saving fetched jobs writes only new, changed and reopened ones, and closing a board closes the jobs it no longer
-- lists. Only the service role runs either. Runs in a transaction that is rolled back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(8);

insert into postings (source, board, external_id, title, company, url, description, closed_at) values
  ('lever', 'acme', 'same', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/same', 'Saved description.', null),
  ('lever', 'acme', 'renamed', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/renamed', 'Saved.', null),
  ('lever', 'acme', 'closed', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/closed', 'Saved.', now());
create temp table before as select external_id, ctid as row_location from postings where board = 'acme';

create temp table saved as
select * from save_postings(
  '[{"source": "lever", "board": "acme", "external_id": "same", "title": "Engineer", "company": "Acme", "location": null,
     "url": "https://jobs.lever.co/acme/same", "posted_at": null, "workplace_type": null},
    {"source": "lever", "board": "acme", "external_id": "renamed", "title": "Senior Engineer", "company": "Acme", "location": null,
     "url": "https://jobs.lever.co/acme/renamed", "description": "Saved.", "posted_at": null, "workplace_type": null},
    {"source": "lever", "board": "acme", "external_id": "closed", "title": "Engineer", "company": "Acme", "location": null,
     "url": "https://jobs.lever.co/acme/closed", "description": "Saved.", "posted_at": null, "workplace_type": null},
    {"source": "lever", "board": "acme", "external_id": "new", "title": "Designer", "company": "Acme", "location": null,
     "url": "https://jobs.lever.co/acme/new", "posted_at": null, "workplace_type": null}]'::jsonb
);

select is(
  (select array_agg(s.id = p.id order by s.external_id) from saved s join postings p using (source, external_id)),
  array[true, true, true, true],
  'every job comes back with its id'
);
select is(
  (select p.ctid = b.row_location from postings p join before b using (external_id) where external_id = 'same'),
  true,
  'an unchanged job is not rewritten'
);
select is(
  (select description from postings where external_id = 'same'),
  'Saved description.',
  'a job sent without a description keeps the saved one'
);
select is((select title from postings where external_id = 'renamed'), 'Senior Engineer', 'a changed job is updated');
select is((select closed_at from postings where external_id = 'closed'), null, 'a closed job listed again reopens');

select is(close_unlisted_postings('lever', 'acme', array['same', 'renamed', 'closed']), 1, 'closing counts the unlisted job');
select is(
  (select array_agg(external_id order by external_id) from postings where board = 'acme' and closed_at is not null),
  array['new'],
  'only the job the board no longer lists is closed'
);

set local role authenticated;
select throws_ok(
  $$select * from save_postings('[]'::jsonb)$$,
  '42501',
  null,
  'a signed-in user cannot save jobs'
);
reset role;

select * from finish();
rollback;
