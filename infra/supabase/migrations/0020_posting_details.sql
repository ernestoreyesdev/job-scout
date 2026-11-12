-- Facts read from the posting text by the scoring call. Null means the posting doesn't say.
alter table public.postings
  add column salary_min numeric,
  add column salary_max numeric,
  add column salary_currency text,
  add column salary_period text check (salary_period in ('year', 'month', 'week', 'day', 'hour')),
  add column clearance text,
  add column visa_sponsorship text check (visa_sponsorship in ('yes', 'no')),
  add column years_experience integer,
  add column tech_stack text[] not null default '{}',
  add column details_extracted_at timestamptz;
