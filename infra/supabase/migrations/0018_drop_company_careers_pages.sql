-- Company names link to their job board page only.
alter table public.companies
  drop column careers_page_url,
  drop column careers_page_checked_at;
