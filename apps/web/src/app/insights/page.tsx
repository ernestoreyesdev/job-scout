import type { Metadata } from "next";
import { Suspense } from "react";

import { AccuracyTable } from "@/components/accuracy-table";
import { SectionCard } from "@/components/section-card";
import { StatTile } from "@/components/stat-tile";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageReady } from "@/components/web-vitals";
import { FUNNEL_STAGES, FOLLOW_UP_DAYS, GHOST_JOB_DAYS } from "@/lib/db";
import { MIN_LABELED, accuracyByCut, funnel, statsBySource, type FunnelJob, type FunnelRow } from "@/lib/insights";
import { getSignedInSource } from "@/lib/repository";

const PERCENT = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
const SOURCE_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  smartrecruiters: "SmartRecruiters",
  workable: "Workable",
  recruitee: "Recruitee",
  workday: "Workday",
  personio: "Personio",
  bamboohr: "BambooHR",
  icims: "iCIMS",
  jobvite: "Jobvite",
  hackernews: "Hacker News",
  manual: "Entered by hand",
};

const ADDED_BY_LABELS: Record<FunnelJob["addedBy"], string> = { search: "Found by search", user: "Added by you" };

export const metadata: Metadata = { title: "Insights" };

export default function InsightsPage() {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        How well the scores match your own judgment, how your applications are going and where your jobs come from.
      </p>
      <Suspense fallback={<div className="mt-8 h-40 animate-pulse rounded-xl border bg-card" />}>
        <InsightsData />
      </Suspense>
    </main>
  );
}

async function InsightsData() {
  const { repository } = await getSignedInSource();
  const [jobs, funnelJobs, followUps, aging] = await Promise.all([
    repository.listScoredJobs(),
    repository.listFunnelJobs(),
    repository.listFollowUpsDue(),
    repository.countAgingJobs(),
  ]);
  const [overall] = funnel(funnelJobs);
  const marked = jobs.filter((job) => job.fit_label !== null);
  const good = marked.filter((job) => job.fit_label === "good").length;
  const sources = statsBySource(jobs);

  return (
    <div className="mt-8 space-y-6">
      <PageReady />
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Jobs scored" value={jobs.length} />
        <StatTile label="Marked good or bad" value={marked.length} note={`${good} good, ${marked.length - good} bad`} />
        <StatTile label="Applied" value={overall?.reached.applied ?? 0} />
        <StatTile
          label="Response rate"
          value={overall?.responseRate == null ? "–" : PERCENT.format(overall.responseRate)}
          note="Screening or further"
        />
      </dl>

      <SectionCard
        title="Scoring accuracy"
        description="From the jobs you marked with thumbs up or down. Precision is how often a job at or above the cut is one you marked good; recall is how many of your good jobs reached it."
      >
        {marked.length < MIN_LABELED && (
          <p className="mb-3 rounded-lg bg-muted/50 px-3 py-2 text-sm">
            Mark {MIN_LABELED - marked.length} more {MIN_LABELED - marked.length === 1 ? "job" : "jobs"}, good and bad,
            before these numbers mean much.
          </p>
        )}
        <AccuracyTable rows={accuracyByCut(jobs)} />
        <p className="mt-3 text-xs text-muted-foreground">
          You can only mark jobs a search kept, and searches drop the lower-scored ones, so recall here counts good jobs
          among those you saw, not every good job that exists.
        </p>
      </SectionCard>

      <SectionCard
        title="Applications"
        description="How far your applications got, from the status history on Jobs. A job counts for every stage up to the furthest it reached."
      >
        {overall ? (
          <>
            <FunnelBars row={overall} />
            <FunnelTable title="By how it was added" rows={funnel(funnelJobs, (job) => ADDED_BY_LABELS[job.addedBy])} />
            <FunnelTable title="By source" rows={funnel(funnelJobs, (job) => SOURCE_LABELS[job.source] ?? job.source)} />
            <FunnelTable title="By resume" rows={funnel(funnelJobs, (job) => job.resume)} />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No applications yet. Set a job to applied on the Tracker or Jobs.</p>
        )}
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Follow-ups due" description={`Jobs still applied ${FOLLOW_UP_DAYS} or more days later, with a draft email on Jobs.`}>
          {followUps.length === 0 ? (
            <p className="text-sm text-muted-foreground">None right now.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {followUps.map((job) => (
                <li key={job.id} className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 truncate">
                    {job.title} <span className="text-muted-foreground">at {job.company}</span>
                  </span>
                  <span className="shrink-0 text-amber-600 dark:text-amber-400">{job.days} days</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
        <SectionCard title="Possible ghost jobs" description={`Postings still listed ${GHOST_JOB_DAYS}+ days after they went up.`}>
          <p className="text-3xl font-semibold tabular-nums">{aging}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {aging === 1 ? "job is" : "jobs are"} flagged on the Tracker and Jobs, along with reposted ones.
          </p>
        </SectionCard>
      </div>

      <SectionCard title="Where your jobs come from" description="Every job scored for you, by the system it came from.">
        {sources.length === 0 ? (
          <p className="text-sm text-muted-foreground">No scored jobs yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Scored</TableHead>
                <TableHead className="text-right">Average score</TableHead>
                <TableHead className="text-right">Good</TableHead>
                <TableHead className="text-right">Bad</TableHead>
                <TableHead className="text-right">Saved</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((row) => (
                <TableRow key={row.source}>
                  <TableCell>{SOURCE_LABELS[row.source] ?? row.source}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.scored}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.averageScore === null ? "–" : Math.round(row.averageScore)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{row.good}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.bad}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.pastNew}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>
    </div>
  );
}

/** The overall funnel as horizontal bars, each stage's width relative to the jobs applied to. */
function FunnelBars({ row }: { row: FunnelRow }) {
  const applied = Math.max(1, row.reached.applied);
  return (
    <ul className="space-y-2">
      {FUNNEL_STAGES.map((stage) => (
        <li key={stage} className="grid grid-cols-[6.5rem_1fr_2.5rem] items-center gap-3 text-sm">
          <span className="capitalize text-muted-foreground">{stage}</span>
          <div className="h-2.5 rounded-full bg-muted">
            <div className="h-2.5 rounded-full bg-primary" style={{ width: `${(row.reached[stage] / applied) * 100}%` }} />
          </div>
          <span className="text-right tabular-nums">{row.reached[stage]}</span>
        </li>
      ))}
    </ul>
  );
}

/** One funnel table: jobs reaching each stage per row, and the response rate. */
function FunnelTable({ title, rows }: { title: string; rows: FunnelRow[] }) {
  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium">{title}</h3>
      <Table className="mt-1">
        <TableHeader>
          <TableRow>
            <TableHead />
            {FUNNEL_STAGES.map((stage) => (
              <TableHead key={stage} className="text-right capitalize">
                {stage}
              </TableHead>
            ))}
            <TableHead className="text-right">Response rate</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label}>
              <TableCell>{row.label}</TableCell>
              {FUNNEL_STAGES.map((stage) => (
                <TableCell key={stage} className="text-right tabular-nums">
                  {row.reached[stage]}
                </TableCell>
              ))}
              <TableCell className="text-right tabular-nums">
                {row.responseRate === null ? "–" : PERCENT.format(row.responseRate)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
