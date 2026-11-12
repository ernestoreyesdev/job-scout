-- The company's own careers page on its website. A check time with no URL means none was found.
alter table public.companies
  add column careers_page_url text,
  add column careers_page_checked_at timestamptz;
