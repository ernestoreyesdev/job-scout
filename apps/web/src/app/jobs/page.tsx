import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AddJob } from "@/components/add-job";
import { JobListFilters } from "@/components/job-filters";
import { JobListSkeleton } from "@/components/job-list-skeleton";
import { JobsTable } from "@/components/jobs-table";
import { Pager } from "@/components/pager";
import { RescoreButton } from "@/components/rescore-button";
import { RunStatus } from "@/components/run-status";
import { PageReady } from "@/components/web-vitals";
import { APPLICATION_STATUSES, JOB_SORTS } from "@/lib/db";
import { parseJobQuery } from "@/lib/job-query";
import { rescoreScope } from "@/lib/runs";
import { getPrimaryResume, getSignedInSource } from "@/lib/repository";

export const metadata: Metadata = { title: "Jobs" };

export default function JobsPage({ searchParams }: PageProps<"/jobs">) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Jobs you&apos;ve saved, applied to or heard back from, including the ones you marked good. Status changes are
        dated for you under Details; use notes for what the app can&apos;t know, like a recruiter&apos;s name.
      </p>
      <Suspense fallback={<JobListSkeleton />}>
        <JobsData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function JobsData({ searchParams }: Pick<PageProps<"/jobs">, "searchParams">) {
  const { repository } = await getSignedInSource();
  const query = parseJobQuery(await searchParams, "status");
  // Rated jobs moved to the Tracker; older links still land there.
  if (query.rated) redirect("/tracker?view=rated");
  const [resume, jobs, companies, runs] = await Promise.all([
    getPrimaryResume(),
    repository.listTrackedJobs("jobs", query.sort, query.page, query.filters),
    repository.listTrackedCompanies("jobs"),
    repository.listRuns(1),
  ]);
  const rescoreRun = runs[0]?.kind === "rescore" && rescoreScope(runs[0]) === "jobs" ? runs[0] : null;
  const stale = resume ? await repository.countStaleJobs(resume.id, "jobs") : 0;

  return (
    <section className="mt-8">
      <PageReady />
      <AddJob />
      {rescoreRun && (
        <div className="mb-6">
          <RunStatus run={rescoreRun} />
        </div>
      )}
      {companies.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No jobs yet. Change a job&apos;s status or mark it good on the Tracker and it shows up here.
        </p>
      ) : (
        <>
          <JobListFilters
            basePath="/jobs"
            query={query}
            companies={companies}
            total={jobs.total}
            statuses={APPLICATION_STATUSES.filter((status) => status !== "new")}
            sorts={JOB_SORTS}
            actions={stale > 0 && <RescoreButton count={stale} scope="jobs" />}
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
