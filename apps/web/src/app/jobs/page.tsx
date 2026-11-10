import { Suspense } from "react";

import { JobListFilters } from "@/components/job-filters";
import { JobsTable } from "@/components/jobs-table";
import { Pager } from "@/components/pager";
import { RescoreButton } from "@/components/rescore-button";
import { APPLICATION_STATUSES } from "@/lib/db";
import { parseJobQuery } from "@/lib/job-query";
import { getSignedInSource } from "@/lib/repository";

export default function JobsPage({ searchParams }: PageProps<"/jobs">) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Jobs you&apos;ve saved, tailored, applied to or heard back from. Status changes are dated for you under
        Details; use notes for what the app can&apos;t know, like a recruiter&apos;s name.
      </p>
      <Suspense fallback={<p className="mt-8 text-sm text-muted-foreground">Loading…</p>}>
        <JobsData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function JobsData({ searchParams }: Pick<PageProps<"/jobs">, "searchParams">) {
  const { repository } = await getSignedInSource();
  const resume = await repository.getPrimaryResume();
  const query = parseJobQuery(await searchParams, resume?.text ? "desc" : "posted");
  const [jobs, companies] = await Promise.all([
    repository.listTrackedJobs("jobs", query.sort, query.page, query.filters),
    repository.listTrackedCompanies("jobs"),
  ]);
  const stale = resume ? await repository.countStaleJobs(resume.id) : 0;

  return (
    <section className="mt-8">
      {companies.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No jobs yet. Change a job&apos;s status on the Tracker and it shows up here.
        </p>
      ) : (
        <>
          <JobListFilters
            basePath="/jobs"
            query={query}
            companies={companies}
            total={jobs.total}
            statuses={APPLICATION_STATUSES.filter((status) => status !== "new")}
          />
          {stale > 0 && (
            <div className="mt-2 flex justify-end">
              <RescoreButton count={stale} />
            </div>
          )}
          {jobs.total === 0 && <p className="mt-4 text-sm text-muted-foreground">No jobs match these filters.</p>}
          <div className="mt-3">
            <JobsTable jobs={jobs.items} showNotes canRemoveFromTracker={false} currentResumeId={resume?.id ?? null} />
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
