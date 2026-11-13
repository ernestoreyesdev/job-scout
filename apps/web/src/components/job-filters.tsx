"use client";

import Link from "next/link";
import type { ChangeEvent, ReactNode } from "react";

import { APPLICATION_STATUSES, type ApplicationStatusRow, type JobSort } from "@/lib/db";
import { jobListHref, type JobQuery } from "@/lib/job-query";

const SORT_LABELS: Record<JobSort, string> = {
  status: "Furthest along",
  desc: "Best match",
  asc: "Lowest score",
  posted: "Newest posted",
  added: "Recently added",
};

const PILL = "h-8 rounded-full border border-input bg-transparent px-3 text-sm shadow-xs hover:border-foreground/30";

/**
 * Filter bar for the Tracker and Jobs, followed by the page's own `actions`. Each control submits the form as a GET
 * as soon as it changes. Jobs whose details were never read pass the salary and clearance filters, and the rated
 * view stays selected through filter changes and Reset.
 */
export function JobListFilters({
  basePath,
  query,
  companies,
  total,
  actions,
  statuses = APPLICATION_STATUSES,
  sorts = ["desc", "asc", "posted", "added"],
}: {
  basePath: string;
  query: JobQuery;
  companies: string[];
  total: number;
  actions?: ReactNode;
  statuses?: readonly ApplicationStatusRow[];
  sorts?: readonly JobSort[];
}) {
  const kept: Record<string, string> = query.rated ? { view: "rated" } : {};
  const active = Object.keys(query.params).length > Object.keys(kept).length;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3 text-sm shadow-xs">
      <form method="get" action={basePath} className="flex flex-1 flex-wrap items-center gap-2">
        {query.rated && <input type="hidden" name="view" value="rated" />}
        <span className="mr-auto pl-1 font-medium">
          {total} {total === 1 ? "job" : "jobs"}
        </span>
        <select name="sort" defaultValue={query.sort} aria-label="Sort" onChange={apply} className={PILL}>
          {sorts.map((value) => (
            <option key={value} value={value}>
              {SORT_LABELS[value]}
            </option>
          ))}
        </select>
        <select name="status" defaultValue={query.filters.status ?? ""} aria-label="Status" onChange={apply} className={PILL}>
          <option value="">Any status</option>
          {statuses.map((status) => (
            <option key={status} value={status}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </option>
          ))}
        </select>
        <select name="company" defaultValue={query.filters.company ?? ""} aria-label="Company" onChange={apply} className={`${PILL} max-w-48`}>
          <option value="">Any company</option>
          {companies.map((company) => (
            <option key={company} value={company}>
              {company}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-muted-foreground">
          Min salary
          <input
            type="number"
            name="salary"
            min={0}
            step={5000}
            defaultValue={query.filters.minSalary ?? ""}
            onBlur={(event) => {
              const changed = event.currentTarget.value !== String(query.filters.minSalary ?? "");
              if (changed) event.currentTarget.form?.requestSubmit();
            }}
            className={`${PILL} w-28`}
          />
        </label>
        <label className="flex h-8 items-center gap-1.5 text-muted-foreground">
          <input type="checkbox" name="open" value="1" defaultChecked={query.filters.hideClosed} onChange={apply} className="size-4 accent-primary" />
          Hide closed
        </label>
        <label className="flex h-8 items-center gap-1.5 text-muted-foreground">
          <input
            type="checkbox"
            name="noclearance"
            value="1"
            defaultChecked={query.filters.hideClearance}
            onChange={apply}
            className="size-4 accent-primary"
          />
          Hide clearance
        </label>
        <button type="submit" className="sr-only">
          Apply filters
        </button>
        {active && (
          <Link href={jobListHref(basePath, kept)} className="text-muted-foreground hover:text-foreground">
            Reset
          </Link>
        )}
      </form>
      {actions}
    </div>
  );
}

function apply(event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
  event.currentTarget.form?.requestSubmit();
}
