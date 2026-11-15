-- A deleted tracked job keeps its score and label in former_scores, without the user, whether the user deleted the job
-- or the whole account; delete_account leaves the copy to the trigger. Jobs rated good while still new become saved,
-- as rating a job good now saves it.
create function public.keep_former_score()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if old.fit_score is not null or old.fit_label is not null then
    insert into public.former_scores (posting_id, fit_score, fit_label, score_model, score_prompt_version, created_at, updated_at)
    values (old.posting_id, old.fit_score, old.fit_label, old.score_model, old.score_prompt_version, old.created_at, old.updated_at);
  end if;
  return old;
end;
$$;

revoke execute on function public.keep_former_score() from public, anon, authenticated;

create trigger applications_keep_former_score
after delete on public.applications
for each row execute function public.keep_former_score();

create or replace function public.delete_account(target uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (select 1 from auth.users u where u.id = target and u.raw_app_meta_data ->> 'role' = 'admin') then
    raise exception 'Admin accounts can''t be deleted.' using errcode = '42501';
  end if;
  delete from auth.users u where u.id = target;
  if found then
    insert into public.account_deletions default values;
  end if;
end;
$$;

update public.applications set status = 'saved', in_tracker = false where fit_label = 'good' and status = 'new';
