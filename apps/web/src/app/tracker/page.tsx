import { Suspense } from "react";

import { ClearTracker } from "@/components/clear-tracker";
import { JobListFilters } from "@/components/job-filters";
import { JobsTable } from "@/components/jobs-table";
import { Pager } from "@/components/pager";
import { RecentRuns } from "@/components/recent-runs";
import { RescoreButton } from "@/components/rescore-button";
import { RunStatus } from "@/components/run-status";
import { SearchForm } from "@/components/search-form";
import { PAGE_SIZE } from "@/lib/db";
import { parseJobQuery } from "@/lib/job-query";
import { getSignedInSource } from "@/lib/repository";

export default function TrackerPage({ searchParams }: PageProps<"/tracker">) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Tracker</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Search by keyword at one company, or leave Company empty to search every company the app has found, and score
        each match against your resume. Jobs you save, apply to or hear back from also appear under Jobs. You always
        submit applications yourself.
      </p>
      <div className="mt-6">
        <SearchForm />
      </div>
      <Suspense fallback={<p className="mt-8 text-sm text-muted-foreground">Loading…</p>}>
        <TrackerData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function TrackerData({ searchParams }: Pick<PageProps<"/tracker">, "searchParams">) {
  const query = parseJobQuery(await searchParams);
  const { repository } = await getSignedInSource();
  const [runs, jobs, resume, companies, trackerTotal] = await Promise.all([
    repository.listRuns(10),
    repository.listTrackedJobs("tracker", query.sort, query.page, query.filters),
    repository.getPrimaryResume(),
    repository.listTrackedCompanies("tracker"),
    repository.countTrackerJobs(),
  ]);
  const stale = resume ? await repository.countStaleJobs(resume.id) : 0;

  return (
    <>
      {runs[0] && <RunStatus run={runs[0]} />}
      <RecentRuns runs={runs} />
      <section className="mt-8">
        {trackerTotal === 0 ? (
          <p className="text-sm text-muted-foreground">No jobs yet. Run a search to find some.</p>
        ) : (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <JobListFilters basePath="/tracker" query={query} companies={companies} />
              <div className="mb-3 flex flex-wrap items-center gap-3">
                {stale > 0 && <RescoreButton count={stale} />}
                <ClearTracker count={trackerTotal} />
              </div>
            </div>
            {jobs.total === 0 && <p className="text-sm text-muted-foreground">No jobs match these filters.</p>}
            <JobsTable
              jobs={jobs.items}
              basePath="/tracker"
              ascending={query.sort === "asc"}
              params={query.params}
              showNotes={false}
              canRemoveFromTracker
              offset={(jobs.page - 1) * PAGE_SIZE}
              currentResumeId={resume?.id ?? null}
            />
            <Pager
              basePath="/tracker"
              page={jobs.page}
              pageCount={jobs.pageCount}
              total={jobs.total}
              params={query.params}
            />
          </>
        )}
      </section>
    </>
  );
}
