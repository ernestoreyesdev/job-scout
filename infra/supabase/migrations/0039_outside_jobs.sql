-- Jobs a user applied to outside the app. A link the app can't read is saved as a manual posting, and each
-- application records whether a search or the user added it.
alter type public.job_source add value 'manual';

alter table public.applications
  add column added_by text not null default 'search' check (added_by in ('search', 'user'));
