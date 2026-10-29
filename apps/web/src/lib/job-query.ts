import { APPLICATION_STATUSES, JOB_SORTS, type ApplicationStatusRow, type JobFilters, type JobSort } from "@/lib/db";

/** The Tracker or Jobs list settings read from the address: sort, filters and page. */
export type JobQuery = {
  sort: JobSort;
  filters: JobFilters;
  page: number;
  params: Record<string, string>;
};

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

/**
 * Reads `?sort=`, `?status=`, `?company=`, `?open=1` and `?page=`, ignoring
 * unknown values. `params` holds the recognized settings other than the page,
 * for links that keep them.
 */
export function parseJobQuery(searchParams: SearchParams): JobQuery {
  const sortValue = first(searchParams.sort);
  const sort = (JOB_SORTS as readonly string[]).includes(sortValue) ? (sortValue as JobSort) : "desc";
  const statusValue = first(searchParams.status);
  const status = (APPLICATION_STATUSES as readonly string[]).includes(statusValue)
    ? (statusValue as ApplicationStatusRow)
    : undefined;
  const company = first(searchParams.company) || undefined;
  const hideClosed = first(searchParams.open) === "1";

  const params: Record<string, string> = {};
  if (sort !== "desc") params.sort = sort;
  if (status) params.status = status;
  if (company) params.company = company;
  if (hideClosed) params.open = "1";

  return { sort, filters: { status, company, hideClosed }, page: Number(first(searchParams.page)) || 1, params };
}

/** A list URL with the given settings, leaving out empty ones. */
export function jobListHref(basePath: string, params: Record<string, string>): string {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value)).toString();
  return query ? `${basePath}?${query}` : basePath;
}
