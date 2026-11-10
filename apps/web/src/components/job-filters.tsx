import Link from "next/link";

import { Button } from "@/components/ui/button";
import { APPLICATION_STATUSES, type ApplicationStatusRow } from "@/lib/db";
import type { JobQuery } from "@/lib/job-query";

const SORT_LABELS = {
  desc: "Best match",
  asc: "Lowest score",
  posted: "Newest posted",
  added: "Recently added",
} as const;

const PILL = "h-8 rounded-full border border-input bg-transparent px-3 text-sm shadow-xs hover:border-foreground/30";

/**
 * Job count plus status, company, sort, salary, closed-job and clearance controls for the Tracker or Jobs; submits
 * as a plain GET to the page. The salary minimum keeps jobs that state a yearly salary reaching it; jobs whose
 * details were never read pass both the salary and clearance filters.
 */
export function JobListFilters({
  basePath,
  query,
  companies,
  total,
  statuses = APPLICATION_STATUSES,
}: {
  basePath: string;
  query: JobQuery;
  companies: string[];
  total: number;
  statuses?: readonly ApplicationStatusRow[];
}) {
  const active = Object.keys(query.params).length > 0;

  return (
    <form
      method="get"
      action={basePath}
      className="flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3 text-sm shadow-xs"
    >
      <span className="mr-auto pl-1 font-medium">
        {total} {total === 1 ? "job" : "jobs"}
      </span>
      <select name="sort" defaultValue={query.sort} aria-label="Sort" className={PILL}>
        {Object.entries(SORT_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <select name="status" defaultValue={query.filters.status ?? ""} aria-label="Status" className={`${PILL} capitalize`}>
        <option value="">Any status</option>
        {statuses.map((status) => (
          <option key={status} value={status}>
            {status}
          </option>
        ))}
      </select>
      <select name="company" defaultValue={query.filters.company ?? ""} aria-label="Company" className={`${PILL} max-w-48`}>
        <option value="">Any company</option>
        {companies.map((company) => (
          <option key={company} value={company}>
            {company}
          </option>
        ))}
      </select>
      <input
        type="number"
        name="salary"
        min={0}
        step={5000}
        defaultValue={query.filters.minSalary ?? ""}
        placeholder="Min salary"
        aria-label="Min yearly salary"
        className={`${PILL} w-32`}
      />
      <label className="flex h-8 items-center gap-1.5 text-muted-foreground">
        <input type="checkbox" name="open" value="1" defaultChecked={query.filters.hideClosed} className="size-4 accent-primary" />
        Hide closed
      </label>
      <label className="flex h-8 items-center gap-1.5 text-muted-foreground">
        <input
          type="checkbox"
          name="noclearance"
          value="1"
          defaultChecked={query.filters.hideClearance}
          className="size-4 accent-primary"
        />
        Hide clearance
      </label>
      <Button type="submit" size="sm" variant="outline" className="rounded-full">
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
