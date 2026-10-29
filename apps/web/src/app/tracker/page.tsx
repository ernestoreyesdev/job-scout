import { Suspense } from "react";

import { ClearTracker } from "@/components/clear-tracker";
import { JobsTable } from "@/components/jobs-table";
import { RunStatus } from "@/components/run-status";
import { SearchForm } from "@/components/search-form";
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
  const ascending = (await searchParams).sort === "asc";
  const { repository } = await getSignedInSource();
  const [runs, jobs] = await Promise.all([repository.listRuns(1), repository.listTrackedJobs("tracker", ascending)]);

  return (
    <>
      {runs[0] && <RunStatus run={runs[0]} />}
      <section className="mt-8">
        {jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No jobs yet. Run a search to find some.</p>
        ) : (
          <>
            <div className="mb-2 flex justify-end">
              <ClearTracker count={jobs.length} />
            </div>
            <JobsTable jobs={jobs} basePath="/tracker" ascending={ascending} showNotes={false} canRemoveFromTracker />
          </>
        )}
      </section>
    </>
  );
}
