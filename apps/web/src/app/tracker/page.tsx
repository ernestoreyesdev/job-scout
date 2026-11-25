import type { Metadata } from "next";
import Link from "next/link";
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
import { PageReady } from "@/components/web-vitals";
import { JOB_SORTS } from "@/lib/db";
import { parseJobQuery } from "@/lib/job-query";
import { rescoreScope, sameRule } from "@/lib/runs";
import { getPrimaryResume, getSignedInSource } from "@/lib/repository";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Tracker" };

const VIEWS = [
  { rated: false, href: "/tracker", label: "New" },
  { rated: true, href: "/tracker?view=rated", label: "Rated" },
] as const;

export default function TrackerPage({ searchParams }: PageProps<"/tracker">) {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Tracker</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Search every company the app knows, or one you name. With your resume, each match gets a fit score. You always
        apply yourself. Rated keeps every job you marked good or bad; a good one is also saved to Jobs.
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
  const params = await searchParams;
  const view = parseJobQuery(params).rated ? "rated" : "tracker";
  const [resume, [latest], searches, alerts, companies, trackerTotal] = await Promise.all([
    getPrimaryResume(),
    repository.listRuns(1),
    repository.listRuns(10, "search"),
    repository.listSearchAlerts(),
    repository.listTrackedCompanies(view),
    repository.countTrackerJobs(),
  ]);
  const query = parseJobQuery(params, resume?.text ? "desc" : "posted");
  const [jobs, stale] = await Promise.all([
    repository.listTrackedJobs(view, query.sort, query.page, query.filters),
    resume && !query.rated ? repository.countStaleJobs(resume.id, "tracker") : 0,
  ]);
  const banner = latest?.kind === "rescore" && rescoreScope(latest) === "jobs" ? null : latest;

  return (
    <>
      <PageReady />
      {banner && !(trackerTotal === 0 && banner.status === "done" && (banner.jobs_added ?? 0) > 0) && <RunStatus run={banner} />}
      <RecentRuns
        runs={searches}
        alerted={searches.filter((search) => alerts.some((alert) => sameRule(alert.rule, search.input))).map((search) => search.id)}
      />
      <section className="mt-8">
        <nav aria-label="Tracker view" className="mb-4 flex gap-1 text-sm">
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
        {query.rated && companies.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No rated jobs yet. Mark a job with thumbs up or down and it shows up here.
          </p>
        ) : !query.rated && trackerTotal === 0 ? (
          <div className="rounded-xl border border-dashed px-6 py-12 text-center">
            {banner?.status === "queued" || banner?.status === "running" ? (
              <>
                <p className="font-medium">Searching…</p>
                <p className="mt-1 text-sm text-muted-foreground">Matches show up here as they&apos;re scored.</p>
              </>
            ) : searches.length > 0 ? (
              <>
                <p className="font-medium">Your Tracker is empty</p>
                <p className="mt-1 text-sm text-muted-foreground">Run a search above to add new matches.</p>
              </>
            ) : (
              <>
                <p className="font-medium">Start your first search</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Enter a job title above and the matches show up here.
                </p>
              </>
            )}
          </div>
        ) : (
          <>
            <JobListFilters
              basePath="/tracker"
              query={query}
              companies={companies}
              total={jobs.total}
              sorts={query.rated ? JOB_SORTS : undefined}
              actions={
                !query.rated && (
                  <>
                    {stale > 0 && <RescoreButton count={stale} scope="tracker" />}
                    <ClearTracker count={trackerTotal} />
                  </>
                )
              }
            />
            {jobs.total === 0 && <p className="mt-4 text-sm text-muted-foreground">No jobs match these filters.</p>}
            <div className="mt-3">
              <JobsTable
                jobs={jobs.items}
                showNotes={false}
                onTracker={!query.rated}
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
  const resume = await getPrimaryResume();
  return <SearchForm hasResume={Boolean(resume?.text)} />;
}
