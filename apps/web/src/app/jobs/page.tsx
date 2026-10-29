import { Suspense } from "react";

import { JobsTable } from "@/components/jobs-table";
import { getSignedInSource } from "@/lib/repository";

export default function JobsPage({ searchParams }: PageProps<"/jobs">) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Jobs you&apos;ve saved, tailored, applied to or heard back from. Use notes for what the app can&apos;t know,
        like a recruiter&apos;s name or the date you applied.
      </p>
      <Suspense fallback={<p className="mt-8 text-sm text-muted-foreground">Loading…</p>}>
        <JobsData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function JobsData({ searchParams }: Pick<PageProps<"/jobs">, "searchParams">) {
  const ascending = (await searchParams).sort === "asc";
  const { repository } = await getSignedInSource();
  const jobs = await repository.listTrackedJobs("jobs", ascending);

  return (
    <section className="mt-8">
      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No jobs yet. Change a job&apos;s status on the Tracker and it shows up here.
        </p>
      ) : (
        <JobsTable jobs={jobs} basePath="/jobs" ascending={ascending} showNotes canRemoveFromTracker={false} />
      )}
    </section>
  );
}
