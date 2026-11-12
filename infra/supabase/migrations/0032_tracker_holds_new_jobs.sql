-- The Tracker holds only new, unrated jobs: jobs already moved past new or rated leave it and stay under Jobs.
update public.applications set in_tracker = false where in_tracker and (status <> 'new' or fit_label is not null);
