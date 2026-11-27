-- Whether the user's marked searches run each morning and email the new strong matches. Users who already marked a
-- search start with it on.
alter table public.profiles add column daily_emails boolean not null default false;

insert into public.profiles (user_id, daily_emails)
select distinct user_id, true from public.search_alerts
on conflict (user_id) do update set daily_emails = true;
