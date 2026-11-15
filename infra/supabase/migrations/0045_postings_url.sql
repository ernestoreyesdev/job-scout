-- Adding a job applied to outside the app looks for a saved job with the same link.
create index postings_url on public.postings (url);
