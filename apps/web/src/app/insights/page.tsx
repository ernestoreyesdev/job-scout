import { Suspense } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FUNNEL_STAGES, FOLLOW_UP_DAYS, GHOST_JOB_DAYS } from "@/lib/db";
import { DEFAULT_CUT, MIN_LABELED, accuracyByCut, funnel, statsBySource, summarizeCosts, type FunnelRow } from "@/lib/insights";
import { getSignedInSource } from "@/lib/repository";
import { cn } from "@/lib/utils";

const PERCENT = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
const DOLLARS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 3 });
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
};
const COST_WINDOW_DAYS = 90;

export default function InsightsPage() {
  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        How well the scores match your own judgment, how your applications are going, where your jobs come from,
        and what searches cost.
      </p>
      <Suspense fallback={<p className="mt-8 text-sm text-muted-foreground">Loading…</p>}>
        <InsightsData />
      </Suspense>
    </main>
  );
}

async function InsightsData() {
  const { repository } = await getSignedInSource();
  const [jobs, runs, funnelJobs, followUps, aging] = await Promise.all([
    repository.listScoredJobs(),
    repository.listRecentRuns(COST_WINDOW_DAYS),
    repository.listFunnelJobs(),
    repository.listFollowUpsDue(),
    repository.countAgingJobs(),
  ]);
  const [overall] = funnel(funnelJobs);
  const marked = jobs.filter((job) => job.fit_label !== null);
  const good = marked.filter((job) => job.fit_label === "good").length;
  const accuracy = accuracyByCut(jobs);
  const sources = statsBySource(jobs);
  const costs = summarizeCosts(runs);

  return (
    <>
      <section className="mt-8">
        <h2 className="text-lg font-semibold">Scoring accuracy</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          From the jobs you marked with thumbs up or down on the Tracker and Jobs: {marked.length} marked, {good} good,{" "}
          {marked.length - good} bad. Precision is how often a job at or above the cut is one you marked good; recall
          is how many of your good jobs reached it.
        </p>
        {marked.length < MIN_LABELED && (
          <p className="mt-2 text-sm">
            Mark {MIN_LABELED - marked.length} more {MIN_LABELED - marked.length === 1 ? "job" : "jobs"}, good and bad,
            before these numbers mean much.
          </p>
        )}
        <Table className="mt-3">
          <TableHeader>
            <TableRow>
              <TableHead>Score at or above</TableHead>
              <TableHead className="text-right">Precision</TableHead>
              <TableHead className="text-right">Recall</TableHead>
              <TableHead className="text-right">Good above</TableHead>
              <TableHead className="text-right">Bad above</TableHead>
              <TableHead className="text-right">Good below</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accuracy.map((row) => (
              <TableRow key={row.cut} className={cn(row.cut === DEFAULT_CUT && "bg-muted/50 font-medium")}>
                <TableCell>{row.cut}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {row.precision === null ? "–" : PERCENT.format(row.precision)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {row.recall === null ? "–" : PERCENT.format(row.recall)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{row.truePositives}</TableCell>
                <TableCell className="text-right tabular-nums">{row.falsePositives}</TableCell>
                <TableCell className="text-right tabular-nums">{row.falseNegatives}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="mt-2 text-xs text-muted-foreground">
          You can only mark jobs a search kept, and searches drop the lower-scored ones, so recall here counts good jobs
          among those you saw, not every good job that exists.
        </p>
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-semibold">Applications</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          How far your applications got, from the status history on Jobs. A job counts for every stage up to the
          furthest it reached; the response rate is screening or further over applied.
        </p>
        {overall ? (
          <>
            <FunnelTable title="Overall" rows={[overall]} />
            <FunnelTable title="By source" rows={funnel(funnelJobs, (job) => SOURCE_LABELS[job.source] ?? job.source)} />
            <FunnelTable title="By resume" rows={funnel(funnelJobs, (job) => job.resume)} />
          </>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">No applications yet. Set a job to applied on the Tracker or Jobs.</p>
        )}
        <h3 className="mt-6 font-medium">Follow-ups due</h3>
        {followUps.length === 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">
            None. Jobs still applied {FOLLOW_UP_DAYS} or more days later show up here, with a draft email on Jobs.
          </p>
        ) : (
          <ul className="mt-1 space-y-1 text-sm">
            {followUps.map((job) => (
              <li key={job.id}>
                {job.title} at {job.company}: <span className="text-amber-600">{job.days} days with no response</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-sm text-muted-foreground">
          {aging} of your jobs {aging === 1 ? "has" : "have"} a posting still listed {GHOST_JOB_DAYS}+ days after it went up,
          a common sign of a ghost job. They&apos;re flagged on the Tracker and Jobs, along with reposted ones.
        </p>
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-semibold">Where your jobs come from</h2>
        <p className="mt-1 text-sm text-muted-foreground">Every job scored for you, by the system it came from.</p>
        {sources.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">No scored jobs yet.</p>
        ) : (
          <Table className="mt-3">
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
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-semibold">What searches cost</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Estimated from each run&apos;s token counts and web searches at Claude Haiku prices, over the last{" "}
          {COST_WINDOW_DAYS} days. Your Anthropic console has the exact bill.
        </p>
        <dl className="mt-3 grid gap-3 sm:grid-cols-3">
          {[
            ["This month", DOLLARS.format(costs.thisMonth)],
            ["Average search", costs.perSearch === null ? "–" : DOLLARS.format(costs.perSearch)],
            [`${costs.runs} runs in ${COST_WINDOW_DAYS} days`, DOLLARS.format(costs.total)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border px-4 py-3">
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}

/** One funnel table: jobs reaching each stage per row, and the response rate. */
function FunnelTable({ title, rows }: { title: string; rows: FunnelRow[] }) {
  return (
    <div className="mt-4">
      <h3 className="font-medium">{title}</h3>
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
