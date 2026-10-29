-- False once the user removes a job from the Tracker view; it stays listed under Jobs.
alter table public.applications add column in_tracker boolean not null default true;
