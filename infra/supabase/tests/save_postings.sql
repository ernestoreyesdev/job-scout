-- Saving fetched jobs writes only new, changed and reopened ones, and closing a board closes the jobs it no longer
-- lists. Only the service role runs either. Runs in a transaction that is rolled back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(11);

insert into postings (source, board, external_id, title, company, url, description, description_hash, workplace_type, closed_at) values
  ('lever', 'acme', 'same', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/same', 'Saved description.', md5('Saved description.'), 'remote', null),
  ('lever', 'acme', 'renamed', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/renamed', 'Saved.', md5('Saved.'), null, null),
  ('lever', 'acme', 'closed', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/closed', 'Saved.', md5('Saved.'), null, now()),
  ('lever', 'acme', 'reworded', 'Engineer', 'Acme', 'https://jobs.lever.co/acme/reworded', 'Old text.', md5('Old text.'), null, null);
insert into posting_embeddings (posting_id, embedding)
select id, array_fill(0.1, array[384])::vector from postings where external_id in ('same', 'reworded');
create temp table before as select external_id, ctid as row_location, xmax::text as row_lock from postings where board = 'acme';

create temp table saved as
select * from save_postings(
  jsonb_build_array(
    jsonb_build_object('source', 'lever', 'board', 'acme', 'external_id', 'same', 'title', 'Engineer', 'company', 'Acme',
      'url', 'https://jobs.lever.co/acme/same', 'description_hash', null),
    jsonb_build_object('source', 'lever', 'board', 'acme', 'external_id', 'renamed', 'title', 'Senior Engineer', 'company', 'Acme',
      'url', 'https://jobs.lever.co/acme/renamed', 'description_hash', md5('Saved.')),
    jsonb_build_object('source', 'lever', 'board', 'acme', 'external_id', 'closed', 'title', 'Engineer', 'company', 'Acme',
      'url', 'https://jobs.lever.co/acme/closed', 'description_hash', md5('Saved.')),
    jsonb_build_object('source', 'lever', 'board', 'acme', 'external_id', 'reworded', 'title', 'Engineer', 'company', 'Acme',
      'url', 'https://jobs.lever.co/acme/reworded', 'description_hash', md5('New text.')),
    jsonb_build_object('source', 'lever', 'board', 'acme', 'external_id', 'new', 'title', 'Designer', 'company', 'Acme',
      'url', 'https://jobs.lever.co/acme/new', 'description_hash', md5('Designs.'))
  )
);

select is(
  (select array_agg(s.id = p.id order by s.external_id) from saved s join postings p using (source, external_id)),
  array[true, true, true, true, true],
  'every job comes back with its id'
);
select is(
  (select p.ctid = b.row_location and p.xmax::text = b.row_lock from postings p join before b using (external_id) where external_id = 'same'),
  true,
  'an unchanged job is neither rewritten nor locked'
);
select is(
  (select description from postings where external_id = 'same'),
  'Saved description.',
  'a job sent without a description hash keeps its saved description'
);
select is(
  (select workplace_type::text from postings where external_id = 'same'),
  'remote',
  'a job sent without a workplace type keeps its saved one'
);
select is((select title from postings where external_id = 'renamed'), 'Senior Engineer', 'a changed job is updated');
select is((select closed_at from postings where external_id = 'closed'), null, 'a closed job listed again reopens');
select is(
  (select description || '|' || description_hash from postings where external_id = 'reworded'),
  '|' || md5('New text.'),
  'a changed description hash clears the saved description'
);
select is(
  (select array_agg(p.external_id order by p.external_id) from posting_embeddings e join postings p on p.id = e.posting_id),
  array['same'],
  'a changed description hash drops the job''s embedding'
);

select is(close_unlisted_postings('lever', 'acme', array['same', 'renamed', 'closed', 'reworded']), 1, 'closing counts the unlisted job');
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
