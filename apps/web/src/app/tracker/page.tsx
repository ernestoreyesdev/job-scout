import { Suspense } from "react";

import { ClearTracker } from "@/components/clear-tracker";
import { JobListFilters } from "@/components/job-filters";
import { JobListSkeleton } from "@/components/job-list-skeleton";
import { JobsTable } from "@/components/jobs-table";
import { Pager } from "@/components/pager";
import { RecentRuns } from "@/components/recent-runs";
import { RescoreButton } from "@/components/rescore-button";
import { RunStatus } from "@/components/run-status";
import { SearchForm } from "@/components/search-form";
import { parseJobQuery } from "@/lib/job-query";
import { getSignedInSource } from "@/lib/repository";

export default function TrackerPage({ searchParams }: PageProps<"/tracker">) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Tracker</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Search every company the app knows, or one you name. With your resume, each match gets a fit score. You always
        apply yourself.
      </p>
      <div className="mt-6">
        <Suspense fallback={<SearchForm hasResume={false} />}>
          <SearchFormData />
        </Suspense>
      </div>
      <Suspense fallback={<JobListSkeleton />}>
        <TrackerData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function TrackerData({ searchParams }: Pick<PageProps<"/tracker">, "searchParams">) {
  const { repository } = await getSignedInSource();
  const resume = await repository.getPrimaryResume();
  const query = parseJobQuery(await searchParams, resume?.text ? "desc" : "posted");
  const [runs, jobs, companies, trackerTotal] = await Promise.all([
    repository.listRuns(10),
    repository.listTrackedJobs("tracker", query.sort, query.page, query.filters),
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
          <div className="rounded-xl border border-dashed px-6 py-12 text-center">
            <p className="font-medium">Start your first search</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Enter a job title above and the matches show up here.
            </p>
          </div>
        ) : (
          <>
            <JobListFilters
              basePath="/tracker"
              query={query}
              companies={companies}
              total={jobs.total}
              actions={
                <>
                  {stale > 0 && <RescoreButton count={stale} />}
                  <ClearTracker count={trackerTotal} />
                </>
              }
            />
            {jobs.total === 0 && <p className="mt-4 text-sm text-muted-foreground">No jobs match these filters.</p>}
            <div className="mt-3">
              <JobsTable
                jobs={jobs.items}
                showNotes={false}
                canRemoveFromTracker
                currentResumeId={resume?.id ?? null}
              />
            </div>
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

async function SearchFormData() {
  const { repository } = await getSignedInSource();
  const resume = await repository.getPrimaryResume();
  return <SearchForm hasResume={Boolean(resume?.text)} />;
}
