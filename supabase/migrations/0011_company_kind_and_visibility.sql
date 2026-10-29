-- What a company is, as labeled by the agent; null until labeled.
alter table public.companies add column kind text
  check (kind in ('employer', 'staffing', 'aggregator'));

-- A row records the user's choice for a company: hidden, or shown even though
-- its kind would hide it by default.
alter table public.hidden_companies add column hidden boolean not null default true;
