-- A user's own corrections to a saved job's title, company and description, shown and scored in place of the job's.
alter table public.applications
  add column edited_title text,
  add column edited_company text,
  add column edited_description text;
