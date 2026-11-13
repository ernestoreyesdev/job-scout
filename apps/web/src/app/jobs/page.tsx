import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AddJob } from "@/components/add-job";
import { JobListFilters } from "@/components/job-filters";
import { JobListSkeleton } from "@/components/job-list-skeleton";
import { JobsTable } from "@/components/jobs-table";
import { Pager } from "@/components/pager";
import { RescoreButton } from "@/components/rescore-button";
import { PageReady } from "@/components/web-vitals";
import { APPLICATION_STATUSES } from "@/lib/db";
import { parseJobQuery } from "@/lib/job-query";
import { getSignedInSource } from "@/lib/repository";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Jobs" };

const VIEWS = [
  { rated: false, href: "/jobs", label: "Saved and beyond" },
  { rated: true, href: "/jobs?view=rated", label: "Rated" },
] as const;

export default function JobsPage({ searchParams }: PageProps<"/jobs">) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Jobs you&apos;ve saved, tailored, applied to or heard back from, and under Rated every job you marked good or
        bad. Status changes are dated for you under Details; use notes for what the app can&apos;t know, like a
        recruiter&apos;s name.
      </p>
      <Suspense fallback={<JobListSkeleton />}>
        <JobsData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function JobsData({ searchParams }: Pick<PageProps<"/jobs">, "searchParams">) {
  const { repository } = await getSignedInSource();
  const resume = await repository.getPrimaryResume();
  const query = parseJobQuery(await searchParams, resume?.text ? "desc" : "posted");
  const view = query.rated ? "rated" : "jobs";
  const [jobs, companies] = await Promise.all([
    repository.listTrackedJobs(view, query.sort, query.page, query.filters),
    repository.listTrackedCompanies(view),
  ]);
  const stale = resume ? await repository.countStaleJobs(resume.id) : 0;

  return (
    <section className="mt-8">
      <PageReady />
      <AddJob />
      <nav aria-label="Jobs view" className="mb-4 flex gap-1 text-sm">
        {VIEWS.map((option) => (
          <Link
            key={option.href}
            href={option.href}
            aria-current={option.rated === query.rated ? "page" : undefined}
            className={cn(
              "rounded-full px-3 py-1 text-muted-foreground transition-colors hover:text-foreground",
              option.rated === query.rated && "bg-muted font-medium text-foreground",
            )}
          >
            {option.label}
          </Link>
        ))}
      </nav>
      {companies.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {query.rated
            ? "No rated jobs yet. Mark a job with thumbs up or down and it shows up here."
            : "No jobs yet. Change a job's status on the Tracker and it shows up here."}
        </p>
      ) : (
        <>
          <JobListFilters
            basePath="/jobs"
            query={query}
            companies={companies}
            total={jobs.total}
            statuses={query.rated ? APPLICATION_STATUSES : APPLICATION_STATUSES.filter((status) => status !== "new")}
            actions={stale > 0 && <RescoreButton count={stale} />}
          />
          {jobs.total === 0 && <p className="mt-4 text-sm text-muted-foreground">No jobs match these filters.</p>}
          <div className="mt-3">
            <JobsTable jobs={jobs.items} showNotes onTracker={false} currentResumeId={resume?.id ?? null} />
          </div>
          <Pager
            basePath="/jobs"
            page={jobs.page}
            pageCount={jobs.pageCount}
            total={jobs.total}
            params={query.params}
          />
        </>
      )}
    </section>
  );
}
