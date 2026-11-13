-- The admin page's storage figures, read without scanning every job: the postings table's size with its indexes, and
-- how many open jobs still need an embedding, counted from a partial index the refresh also reads them by.
drop function public.board_storage();

create index postings_unembedded on public.postings (created_at desc) where closed_at is null and embedding is null;

create function public.storage_totals()
returns table (bytes bigint, unembedded bigint)
language sql
stable
as $$
  select
    pg_total_relation_size('public.postings'),
    (select count(*) from public.postings where closed_at is null and embedding is null);
$$;

revoke execute on function public.storage_totals() from public, anon, authenticated;
