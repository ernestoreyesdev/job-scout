-- Deleting stale jobs looks up closed jobs by when they closed.
create index postings_closed on public.postings (closed_at) where closed_at is not null;
