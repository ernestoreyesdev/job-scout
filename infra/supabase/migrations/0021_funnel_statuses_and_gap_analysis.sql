-- Funnel stages between applying and hearing back, and the on-demand gap analysis of a job against the resume.
alter type public.application_status add value 'screening' after 'applied';
alter type public.application_status add value 'offer' after 'interviewing';

alter table public.applications
  add column gap_analysis jsonb,
  add column gap_analyzed_at timestamptz;
