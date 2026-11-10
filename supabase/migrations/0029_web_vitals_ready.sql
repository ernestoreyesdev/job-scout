-- READY: milliseconds from opening a page (a click, back or forward, or a full load) until its data is on screen.
-- Pages are reported by title rather than path from here on, so the path rows are cleared.
alter table public.web_vitals drop constraint web_vitals_metric_check;
alter table public.web_vitals
  add constraint web_vitals_metric_check check (metric in ('TTFB', 'FCP', 'LCP', 'CLS', 'INP', 'READY'));
delete from public.web_vitals where page like '/%';
