-- App-wide API keys an admin manages, used when a user has no key of their own. RLS is on with no policies,
-- so only the service role (the agent) can read or write them.
create table public.shared_credentials (
  provider text primary key,
  ciphertext text not null,
  hint text not null,
  updated_at timestamptz not null default now()
);

alter table public.shared_credentials enable row level security;

create trigger shared_credentials_touch_updated_at
  before update on public.shared_credentials
  for each row execute function public.touch_updated_at();
