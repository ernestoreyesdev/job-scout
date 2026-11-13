-- Drops the tailored and screening statuses, moving any jobs on them to saved and interviewing. The values are
-- declared in the order Jobs sorts by status, so ordering descending puts offers first and rejections last.
create type public.application_status_next as enum ('new', 'rejected', 'saved', 'applied', 'interviewing', 'offer');

drop trigger applications_record_status on public.applications;

alter table public.applications alter column status drop default;

alter table public.applications
  alter column status type public.application_status_next
  using (case status::text when 'tailored' then 'saved' when 'screening' then 'interviewing' else status::text end)::public.application_status_next;

alter table public.applications alter column status set default 'new';

alter table public.application_events
  alter column status type public.application_status_next
  using (case status::text when 'tailored' then 'saved' when 'screening' then 'interviewing' else status::text end)::public.application_status_next;

drop type public.application_status;

alter type public.application_status_next rename to application_status;

create trigger applications_record_status
  after insert or update of status on public.applications
  for each row execute function public.record_application_status();
