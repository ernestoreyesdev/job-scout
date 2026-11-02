-- The user's own verdict on a job's fit, compared with fit_score to measure scoring accuracy.
alter table public.applications
  add column fit_label text check (fit_label in ('good', 'bad'));
