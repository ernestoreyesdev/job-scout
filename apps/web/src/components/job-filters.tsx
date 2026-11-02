import Link from "next/link";

import { Button } from "@/components/ui/button";
import { APPLICATION_STATUSES, type ApplicationStatusRow } from "@/lib/db";
import type { JobQuery } from "@/lib/job-query";

const SORT_LABELS = {
  desc: "Score, highest first",
  asc: "Score, lowest first",
  posted: "Newest posted",
  added: "Recently added",
} as const;

const SELECT = "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs";

/**
 * Status, company, closed-job, clearance, salary and sort controls for the Tracker or Jobs; submits as a plain GET
 * to the page. The salary minimum only keeps jobs that state a yearly salary reaching it.
 */
export function JobListFilters({
  basePath,
  query,
  companies,
  statuses = APPLICATION_STATUSES,
}: {
  basePath: string;
  query: JobQuery;
  companies: string[];
  statuses?: readonly ApplicationStatusRow[];
}) {
  const active = Object.keys(query.params).length > 0;

  return (
    <form method="get" action={basePath} className="mb-3 flex flex-wrap items-end gap-3 text-sm">
      <label className="space-y-1">
        <span className="block font-medium">Status</span>
        <select name="status" defaultValue={query.filters.status ?? ""} className={SELECT}>
          <option value="">Any</option>
          {statuses.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1">
        <span className="block font-medium">Company</span>
        <select name="company" defaultValue={query.filters.company ?? ""} className={`${SELECT} max-w-48`}>
          <option value="">Any</option>
          {companies.map((company) => (
            <option key={company} value={company}>
              {company}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1">
        <span className="block font-medium">Sort</span>
        <select name="sort" defaultValue={query.sort} className={SELECT}>
          {Object.entries(SORT_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1">
        <span className="block font-medium">Min yearly salary</span>
        <input
          type="number"
          name="salary"
          min={0}
          step={5000}
          defaultValue={query.filters.minSalary ?? ""}
          placeholder="Any"
          className={`${SELECT} w-32`}
        />
      </label>
      <label className="flex h-9 items-center gap-1.5">
        <input type="checkbox" name="open" value="1" defaultChecked={query.filters.hideClosed} className="size-4 accent-primary" />
        Hide closed
      </label>
      <label className="flex h-9 items-center gap-1.5">
        <input
          type="checkbox"
          name="noclearance"
          value="1"
          defaultChecked={query.filters.hideClearance}
          className="size-4 accent-primary"
        />
        Hide clearance jobs
      </label>
      <Button type="submit" size="sm" variant="outline">
        Apply
      </Button>
      {active && (
        <Link href={basePath} className="text-muted-foreground hover:text-foreground">
          Reset
        </Link>
      )}
    </form>
  );
}
