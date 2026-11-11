import type { Metadata } from "next";
import { Suspense } from "react";

import { AccuracyTable } from "@/components/accuracy-table";
import { KeyForm } from "@/components/key-form";
import { SectionCard } from "@/components/section-card";
import { StatTile } from "@/components/stat-tile";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageReady } from "@/components/web-vitals";
import { callAgent } from "@/lib/agent";
import type { AgentRunRow, ApplicationStatusRow, CompanyKindRow, FitLabelRow, RunUsage, WEB_VITALS } from "@/lib/db";
import { MIN_LABELED, accuracyByCut, runCost, summarizeCosts } from "@/lib/insights";
import { getAdminSource } from "@/lib/repository";
import { cn } from "@/lib/utils";

const DOLLARS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const PERCENT = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
const DAY_MS = 24 * 60 * 60 * 1000;
const ACTIVE_DAYS = 7;
const CHART_DAYS = 14;

type StepCalls = RunUsage & {
  step: string;
  calls: number;
  errors: number;
  median_ms: number;
  p95_ms: number;
};

const STEP_LABELS: Record<string, string> = {
  companies: "Checking companies",
  hacker_news: "Hacker News posts",
  titles: "Related titles",
  shortlist: "Shortlisting",
  examples: "Picking labeled examples",
  scoring: "Scoring",
  discovery: "Finding companies",
  naming: "Labeling companies",
  gap_analysis: "Gap analysis",
  follow_up: "Follow-up drafts",
  other: "Other",
};

type BoardFetches = { fetches: number; failures: number; cached: number; median_ms: number; max_ms: number; jobs: number };

type AdminStats = {
  generated_at: string;
  days: number;
  max_missed_checks: number;
  users: { id: string; email: string | null; created_at: string | null; last_sign_in_at: string | null }[];
  runs: (Pick<AgentRunRow, "id" | "user_id" | "kind" | "status" | "error" | "error_code" | "created_at" | "finished_at" | "usage" | "timings"> & {
    unreachable_boards: string[];
  })[];
  calls: StepCalls[];
  boards: {
    sources: (BoardFetches & { source: string; total_ms: number })[];
    slowest: (BoardFetches & { board: string; source: string })[];
  };
  vitals: { page: string; metric: (typeof WEB_VITALS)[number]; count: number; median: number; p75: number }[];
  model_weeks: {
    week: string;
    calls: number;
    errors: number;
    broken: number;
    median_ms: number | null;
    cache_share: number | null;
    searches: number;
    search_usage: Partial<RunUsage>;
    scored: number;
    average_score: number | null;
    rated: number;
    good: number;
  }[];
  prompt_versions: { step: string; prompt_version: string | null; model: string; calls: number; first: string; last: string }[];
  score_versions: {
    prompt_version: string | null;
    model: string | null;
    scored: number;
    average_score: number;
    rated: number;
    good: number;
    predicted_good: number;
    predicted_good_correct: number;
  }[];
  evals: { eval: string; model: string | null; prompt_version: string | null; metrics: Record<string, unknown>; cost: number | null; created_at: string }[];
  refreshes: {
    id: string;
    started_at: string;
    finished_at: string | null;
    boards: number;
    jobs: number;
    new_jobs: number;
    closed_jobs: number;
    embedded_jobs: number;
    deleted_jobs: number;
    failures: number;
  }[];
  refresh_boards: {
    board: string;
    source: string;
    median_ms: number | null;
    last_ms: number | null;
    last_outcome: string | null;
    failures: number;
    open_jobs: number;
    embedded: number;
    saved_jobs: number;
    bytes: number;
  }[];
  companies: { name: string; source: string; board: string; kind: CompanyKindRow | null; open_jobs: number; missed_checks: number }[];
  labels: { fit_score: number | null; fit_label: FitLabelRow | null }[];
  applications: { user_id: string; status: ApplicationStatusRow }[];
};

export const metadata: Metadata = { title: "Admin" };

export default function AdminPage() {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
      <p className="mt-1 text-sm text-muted-foreground">The app&apos;s shared Anthropic key and how everyone is using it.</p>
      <Suspense fallback={<div className="mt-8 h-40 animate-pulse rounded-xl border bg-card" />}>
        <AdminData />
      </Suspense>
    </main>
  );
}

async function AdminData() {
  await getAdminSource();
  const [key, stats] = await Promise.all([
    callAgent<{ hint: string | null; fallback: boolean }>("/admin/anthropic-key", { method: "GET" }),
    callAgent<AdminStats>("/admin/stats", { method: "GET" }),
  ]);
  const now = new Date(stats.generated_at).getTime();
  const activeSince = now - ACTIVE_DAYS * DAY_MS;
  const searches = stats.runs.filter((run) => run.kind === "search");
  const active = new Set(stats.runs.filter((run) => new Date(run.created_at).getTime() >= activeSince).map((run) => run.user_id));
  const costs = summarizeCosts(stats.runs);
  const marked = stats.labels.filter((label) => label.fit_label !== null);
  const kinds = { employer: 0, staffing: 0, aggregator: 0, unlabeled: 0 };
  for (const company of stats.companies) kinds[company.kind ?? "unlabeled"] += 1;
  const openJobs = stats.companies.reduce((sum, company) => sum + company.open_jobs, 0);

  const days = Array.from({ length: CHART_DAYS }, (_, i) => {
    const start = new Date(now - (CHART_DAYS - 1 - i) * DAY_MS);
    start.setHours(0, 0, 0, 0);
    const end = start.getTime() + DAY_MS;
    const runs = searches.filter((run) => {
      const at = new Date(run.created_at).getTime();
      return at >= start.getTime() && at < end;
    });
    return { label: isoDate(start), done: runs.filter((run) => run.status === "done").length, other: runs.filter((run) => run.status !== "done").length };
  });
  const busiest = Math.max(1, ...days.map((day) => day.done + day.other));

  const users = stats.users
    .map((user) => {
      const runs = stats.runs.filter((run) => run.user_id === user.id);
      return {
        ...user,
        searches: runs.filter((run) => run.kind === "search").length,
        spend: runs.reduce((sum, run) => sum + runCost(run.usage), 0),
        applied: stats.applications.filter((application) => application.user_id === user.id && application.status !== "saved").length,
      };
    })
    .sort((a, b) => b.spend - a.spend);

  return (
    <div className="mt-8 space-y-6">
      <PageReady />
      <SectionCard
        title="Shared Anthropic key"
        description="Runs use a user's own key when they saved one before, otherwise this key, otherwise the ANTHROPIC_API_KEY setting. Anthropic checks a new key before it's saved."
      >
        <KeyForm hint={key.hint} fallback={key.fallback} />
      </SectionCard>

      <SectionCard title="Usage" description={`The last ${stats.days} days, estimated at Claude Haiku prices. Your Anthropic console has the exact bill.`}>
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Users" value={stats.users.length} note={`${active.size} active in the last ${ACTIVE_DAYS} days`} />
          <StatTile
            label="Searches"
            value={searches.length}
            note={`${searches.filter((run) => run.status === "failed").length} failed, ${searches.filter((run) => run.status === "stopped").length} stopped`}
          />
          <StatTile label="Spend" value={DOLLARS.format(costs.total)} note={`${DOLLARS.format(costs.thisMonth)} this month`} />
          <StatTile label="Average search" value={costs.perSearch === null ? "–" : DOLLARS.format(costs.perSearch)} />
        </dl>
        <div className="mt-6">
          <p className="text-sm font-medium">Searches per day</p>
          <div className="mt-3 flex h-32 items-end gap-1.5" role="img" aria-label={`Searches per day over the last ${CHART_DAYS} days`}>
            {days.map((day) => (
              <div key={day.label} className="flex h-full flex-1 flex-col justify-end" title={`${day.label}: ${day.done} done, ${day.other} failed or stopped`}>
                {day.other > 0 && <div className="rounded-t-sm bg-muted-foreground/30" style={{ height: `${(day.other / busiest) * 100}%` }} />}
                {day.done > 0 && (
                  <div className={day.other ? "bg-primary" : "rounded-t-sm bg-primary"} style={{ height: `${(day.done / busiest) * 100}%` }} />
                )}
                {day.done + day.other === 0 && <div className="h-px bg-border" />}
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-xs text-muted-foreground">
            <span>{days[0].label}</span>
            <span>Done, and failed or stopped (gray)</span>
            <span>{days.at(-1)!.label}</span>
          </div>
        </div>
      </SectionCard>

      <HealthSection stats={stats} />

      <PageSpeedSection vitals={stats.vitals} days={stats.days} />

      <SpeedSection runs={searches} />

      <BoardSection boards={stats.boards} companies={stats.companies} days={stats.days} />

      <RefreshSection refreshes={stats.refreshes} boards={stats.refresh_boards} companies={stats.companies} days={stats.days} />

      <SectionCard
        title="Claude calls by step"
        description={`Every call over the last ${stats.days} days. Cache hits are the share of input read from the prompt cache.`}
      >
        {stats.calls.length === 0 ? (
          <p className="text-sm text-muted-foreground">No calls recorded yet. Runs record their calls from now on.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Step</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">Errors</TableHead>
                <TableHead className="text-right">Median</TableHead>
                <TableHead className="text-right">Slowest 5%</TableHead>
                <TableHead className="text-right">Cache hits</TableHead>
                <TableHead className="text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stats.calls.map((row) => {
                const input = row.input_tokens + row.cache_read_input_tokens + row.cache_creation_input_tokens;
                return (
                  <TableRow key={row.step}>
                    <TableCell>{STEP_LABELS[row.step] ?? row.step}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.calls.toLocaleString()}</TableCell>
                    <TableCell className={cn("text-right tabular-nums", row.errors > 0 && "text-destructive")}>{row.errors}</TableCell>
                    <TableCell className="text-right tabular-nums">{seconds(row.median_ms)}</TableCell>
                    <TableCell className="text-right tabular-nums">{seconds(row.p95_ms)}</TableCell>
                    <TableCell className="text-right tabular-nums">{input ? PERCENT.format(row.cache_read_input_tokens / input) : "–"}</TableCell>
                    <TableCell className="text-right tabular-nums">{DOLLARS.format(runCost(row))}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      <ModelQualitySection stats={stats} />

      <SectionCard title="Users" description={`Searches and spend over the last ${stats.days} days; applied counts every job past saved.`}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Joined</TableHead>
              <TableHead>Last sign-in</TableHead>
              <TableHead className="text-right">Searches</TableHead>
              <TableHead className="text-right">Spend</TableHead>
              <TableHead className="text-right">Applied</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="max-w-64 truncate">{user.email ?? "–"}</TableCell>
                <TableCell className="tabular-nums">{user.created_at ? isoDate(new Date(user.created_at)) : "–"}</TableCell>
                <TableCell className="tabular-nums">{user.last_sign_in_at ? isoDate(new Date(user.last_sign_in_at)) : "Never"}</TableCell>
                <TableCell className="text-right tabular-nums">{user.searches}</TableCell>
                <TableCell className="text-right tabular-nums">{DOLLARS.format(user.spend)}</TableCell>
                <TableCell className="text-right tabular-nums">{user.applied}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </SectionCard>

      <SectionCard title="Company directory" description="Every company searches can check, shared by all users.">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Companies" value={stats.companies.length.toLocaleString()} note={`${openJobs.toLocaleString()} open jobs`} />
          <StatTile label="Employers" value={kinds.employer} />
          <StatTile label="Staffing and aggregators" value={kinds.staffing + kinds.aggregator} note="Skipped unless a user shows them" />
          <StatTile label="Not labeled yet" value={kinds.unlabeled} />
        </dl>
      </SectionCard>

      <SectionCard
        title="Scoring accuracy across everyone"
        description={`${marked.length} jobs marked good or bad by all users.${marked.length < MIN_LABELED ? ` These numbers need about ${MIN_LABELED} before they mean much.` : ""}`}
      >
        <AccuracyTable rows={accuracyByCut(stats.labels)} />
      </SectionCard>
    </div>
  );
}

/** "2026-11-10", in local time. */
function isoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** "1.4 s" or "850 ms". */
function seconds(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

/** Median and slowest finished search, and the average time searches spent in each step. */
function SpeedSection({ runs }: { runs: AdminStats["runs"] }) {
  const done = runs.filter((run) => run.status === "done" && run.finished_at);
  const durations = done
    .map((run) => new Date(run.finished_at!).getTime() - new Date(run.created_at).getTime())
    .sort((a, b) => a - b);
  const timed = done.filter((run) => run.timings);
  const steps = Object.entries(
    timed.reduce<Record<string, number>>((totals, run) => {
      for (const [step, ms] of Object.entries(run.timings!)) totals[step] = (totals[step] ?? 0) + ms;
      return totals;
    }, {}),
  )
    .map(([step, total]) => ({ step, average: total / timed.length }))
    .sort((a, b) => b.average - a.average);
  const longest = Math.max(1, ...steps.map((row) => row.average));

  return (
    <SectionCard title="Search speed" description="Finished searches, from start to the last saved job.">
      <dl className="grid gap-3 sm:grid-cols-3">
        <StatTile label="Finished searches" value={done.length} />
        <StatTile label="Median" value={durations.length ? seconds(durations[Math.floor(durations.length / 2)]) : "–"} />
        <StatTile label="Slowest" value={durations.length ? seconds(durations.at(-1)!) : "–"} />
      </dl>
      <p className="mt-6 text-sm font-medium">Average time per step</p>
      {steps.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">No step timings yet. Searches record them from now on.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {steps.map((row) => (
            <li key={row.step} className="grid grid-cols-[9rem_1fr_4rem] items-center gap-3 text-sm">
              <span className="text-muted-foreground">{STEP_LABELS[row.step] ?? row.step}</span>
              <div className="h-2.5 rounded-full bg-muted">
                <div className="h-2.5 rounded-full bg-primary" style={{ width: `${(row.average / longest) * 100}%` }} />
              </div>
              <span className="text-right tabular-nums">{seconds(Math.round(row.average))}</span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

const RECENT_FAILURES = 8;

/** Failed and timed-out runs, and the boards searches couldn't reach or found gone. */
function HealthSection({ stats }: { stats: AdminStats }) {
  const emails = new Map(stats.users.map((user) => [user.id, user.email ?? "–"]));
  const names = new Map(stats.companies.map((company) => [`${company.source}/${company.board}`, company.name]));
  const failed = stats.runs.filter((run) => run.status === "failed");
  const timedOut = failed.filter((run) => run.error_code === "timed_out").length;
  const unreachable = new Map<string, { count: number; last: string }>();
  for (const run of stats.runs) {
    for (const board of run.unreachable_boards ?? []) {
      const seen = unreachable.get(board);
      unreachable.set(board, { count: (seen?.count ?? 0) + 1, last: seen && seen.last > run.created_at ? seen.last : run.created_at });
    }
  }
  const missing = stats.companies.filter((company) => company.missed_checks > 0).sort((a, b) => b.missed_checks - a.missed_checks);
  const problems = [
    ...[...unreachable.entries()].map(([board, seen]) => ({
      key: `unreachable-${board}`,
      name: names.get(board) ?? board,
      board,
      problem: `Couldn't be reached in ${seen.count} ${seen.count === 1 ? "search" : "searches"}, last ${isoDate(new Date(seen.last))}`,
    })),
    ...missing.map((company) => ({
      key: `missing-${company.source}/${company.board}`,
      name: company.name,
      board: `${company.source}/${company.board}`,
      problem: `Board not found in ${company.missed_checks} ${company.missed_checks === 1 ? "search" : "searches"} in a row; removed at ${stats.max_missed_checks}`,
    })),
  ];

  return (
    <SectionCard title="Health" description={`Problems over the last ${stats.days} days.`}>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Failed runs" value={failed.length} note={`of ${stats.runs.length} runs`} />
        <StatTile label="Timed out" value={timedOut} note="Stopped after 10 minutes" />
        <StatTile label="Boards unreachable" value={unreachable.size} />
        <StatTile label="Boards going missing" value={missing.length} />
      </dl>
      <p className="mt-6 text-sm font-medium">Recent failures</p>
      {failed.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">None.</p>
      ) : (
        <ul className="mt-2 divide-y rounded-lg border text-sm">
          {failed.slice(0, RECENT_FAILURES).map((run) => (
            <li key={run.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
              <span className="w-24 shrink-0 text-muted-foreground tabular-nums">{isoDate(new Date(run.created_at))}</span>
              <span className="w-56 shrink-0 truncate text-muted-foreground">{emails.get(run.user_id) ?? "–"}</span>
              <span className="shrink-0 capitalize">{run.kind}</span>
              {run.error_code && (
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{run.error_code.replace("_", " ")}</span>
              )}
              <span className="min-w-0 flex-1 text-destructive">{run.error ?? "No error message"}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-6 text-sm font-medium">Problem boards</p>
      {problems.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">None.</p>
      ) : (
        <ul className="mt-2 divide-y rounded-lg border text-sm">
          {problems.map((row) => (
            <li key={row.key} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
              <span className="font-medium">{row.name}</span>
              <span className="font-mono text-xs text-muted-foreground">{row.board}</span>
              <span className="ml-auto text-muted-foreground">{row.problem}</span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

/** Core Web Vitals thresholds: at or under the first is good, over the second is poor. READY borrows LCP's, since both mean the content is visible. */
const VITAL_THRESHOLDS = {
  TTFB: [800, 1800],
  FCP: [1800, 3000],
  LCP: [2500, 4000],
  INP: [200, 500],
  CLS: [0.1, 0.25],
  READY: [2500, 4000],
} as const;
const VITAL_COLUMNS = [
  { metric: "READY", label: "Data shown", stat: "median" },
  { metric: "READY", label: "Data shown (75%)", stat: "p75" },
  { metric: "TTFB", label: "First byte", stat: "p75" },
  { metric: "LCP", label: "Main content", stat: "p75" },
  { metric: "INP", label: "Response to input", stat: "p75" },
  { metric: "CLS", label: "Layout shift", stat: "p75" },
] as const;

/** How fast each page loads for real users, from the measurements their browsers reported. */
function PageSpeedSection({ vitals, days }: { vitals: AdminStats["vitals"]; days: number }) {
  const pages = [...new Set(vitals.map((row) => row.page))];
  const find = (page: string, metric: string) => vitals.find((row) => row.page === page && row.metric === metric);

  return (
    <SectionCard
      title="Page speed"
      description={`What signed-in users' browsers measured over the last ${days} days. Data shown is from opening a page, by a click or a full load, until its data is on screen; the other columns only cover full loads in most browsers. 75% means three in four were at least this fast. Green is good, amber needs work and red is poor.`}
    >
      {pages.length === 0 ? (
        <p className="text-sm text-muted-foreground">No measurements yet. Browsers report them from now on.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Page</TableHead>
              <TableHead className="text-right">Loads</TableHead>
              {VITAL_COLUMNS.map((column) => (
                <TableHead key={column.label} className="text-right">
                  {column.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {pages.map((page) => (
              <TableRow key={page}>
                <TableCell>{page}</TableCell>
                <TableCell className="text-right tabular-nums">{find(page, "READY")?.count ?? find(page, "TTFB")?.count ?? "–"}</TableCell>
                {VITAL_COLUMNS.map((column) => {
                  const row = find(page, column.metric);
                  const value = row?.[column.stat];
                  const [good, poor] = VITAL_THRESHOLDS[column.metric];
                  return (
                    <TableCell
                      key={column.label}
                      className={cn(
                        "text-right tabular-nums",
                        value !== undefined &&
                          (value <= good
                            ? "text-emerald-600 dark:text-emerald-400"
                            : value > poor
                              ? "text-destructive"
                              : "text-amber-600 dark:text-amber-400"),
                      )}
                    >
                      {value === undefined ? "–" : column.metric === "CLS" ? value.toFixed(2) : seconds(Math.round(value))}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </SectionCard>
  );
}

/** Where the "Checking companies" step spends its time: totals per job system and the slowest boards. */
function BoardSection({ boards, companies, days }: { boards: AdminStats["boards"]; companies: AdminStats["companies"]; days: number }) {
  const names = new Map(companies.map((company) => [`${company.source}/${company.board}`, company.name]));

  return (
    <SectionCard
      title="Board fetches"
      description={`Every board searches checked over the last ${days} days, timed from the first request to the last page, retry included. Boards refreshed within the last 25 hours are read from saved jobs and count as from cache.`}
    >
      {boards.sources.length === 0 ? (
        <p className="text-sm text-muted-foreground">No board fetches recorded yet. Searches across all companies record them from now on.</p>
      ) : (
        <>
          <p className="text-sm font-medium">By job system</p>
          <Table className="mt-1">
            <TableHeader>
              <TableRow>
                <TableHead>Job system</TableHead>
                <TableHead className="text-right">Fetches</TableHead>
                <TableHead className="text-right">From cache</TableHead>
                <TableHead className="text-right">Failed</TableHead>
                <TableHead className="text-right">Median</TableHead>
                <TableHead className="text-right">Slowest</TableHead>
                <TableHead className="text-right">Total time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {boards.sources.map((row) => (
                <TableRow key={row.source}>
                  <TableCell className="font-mono text-xs">{row.source}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.fetches}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.cached}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", row.failures > 0 && "text-destructive")}>{row.failures}</TableCell>
                  <TableCell className="text-right tabular-nums">{seconds(row.median_ms)}</TableCell>
                  <TableCell className="text-right tabular-nums">{seconds(row.max_ms)}</TableCell>
                  <TableCell className="text-right tabular-nums">{seconds(row.total_ms)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-6 text-sm font-medium">Slowest boards</p>
          <Table className="mt-1">
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>Board</TableHead>
                <TableHead className="text-right">Median</TableHead>
                <TableHead className="text-right">Slowest</TableHead>
                <TableHead className="text-right">Jobs</TableHead>
                <TableHead className="text-right">Failed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {boards.slowest.map((row) => (
                <TableRow key={row.board}>
                  <TableCell>{names.get(row.board) ?? "–"}</TableCell>
                  <TableCell className="max-w-56 truncate font-mono text-xs" title={row.board}>
                    {row.board}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{seconds(row.median_ms)}</TableCell>
                  <TableCell className="text-right tabular-nums">{seconds(row.max_ms)}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.jobs.toLocaleString()}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", row.failures > 0 && "text-destructive")}>{row.failures}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-3 text-xs text-muted-foreground">
            Boards download at the same time, a few at once, so the step takes less than the total time added up.
          </p>
        </>
      )}
    </SectionCard>
  );
}

/** "2026-11-11 10:04 UTC". */
function utcTime(iso: string): string {
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}

/** "640 KB" or "12.3 MB". */
function size(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

/**
 * The daily board refreshes, newest first, and every board's refresh fetch times with the jobs it has saved and the
 * database space they take; slowest boards first.
 */
function RefreshSection({
  refreshes,
  boards,
  companies,
  days,
}: {
  refreshes: AdminStats["refreshes"];
  boards: AdminStats["refresh_boards"];
  companies: AdminStats["companies"];
  days: number;
}) {
  const names = new Map(companies.map((company) => [`${company.source}/${company.board}`, company.name]));
  const totalBytes = boards.reduce((sum, row) => sum + row.bytes, 0);
  const unembedded = boards.reduce((sum, row) => sum + row.open_jobs - row.embedded, 0);
  const worth = boards.filter((row, rank) => rank < SLOWEST_BOARDS || row.failures > 0);

  return (
    <SectionCard
      title="Board refresh"
      description={`Every directory board is fetched once a day and its jobs saved, so searches read them from the database. Refreshes over the last ${days} days.`}
    >
      {refreshes.length === 0 ? (
        <p className="text-sm text-muted-foreground">No refreshes yet. The first one runs at 10:00 UTC.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Started</TableHead>
              <TableHead className="text-right">Took</TableHead>
              <TableHead className="text-right">Boards</TableHead>
              <TableHead className="text-right">Jobs</TableHead>
              <TableHead className="text-right">New</TableHead>
              <TableHead className="text-right">Closed</TableHead>
              <TableHead className="text-right">Embedded</TableHead>
              <TableHead className="text-right">Deleted</TableHead>
              <TableHead className="text-right">Failed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {refreshes.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="tabular-nums">{utcTime(row.started_at)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {row.finished_at ? seconds(new Date(row.finished_at).getTime() - new Date(row.started_at).getTime()) : "Unfinished"}
                </TableCell>
                <TableCell className="text-right tabular-nums">{row.boards}</TableCell>
                <TableCell className="text-right tabular-nums">{row.jobs.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{row.new_jobs.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{row.closed_jobs.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{row.embedded_jobs.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{row.deleted_jobs.toLocaleString()}</TableCell>
                <TableCell className={cn("text-right tabular-nums", row.failures > 0 && "text-destructive")}>{row.failures}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {boards.length > 0 && (
        <>
          <p className="mt-6 text-sm font-medium">
            {boards.length} boards, {size(totalBytes)} saved in all
          </p>
          {unembedded > 0 && (
            <p className="text-xs text-muted-foreground">
              {unembedded.toLocaleString()} open {unembedded === 1 ? "job has" : "jobs have"} no embedding yet, so searches rank{" "}
              {unembedded === 1 ? "it" : "them"} after the rest. Each refresh embeds up to 1,000.
            </p>
          )}
          <p className="mt-4 text-sm font-medium">Slowest and failing boards</p>
          <RefreshBoardTable boards={worth} names={names} />
          {boards.length > worth.length && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-medium">All boards ({boards.length})</summary>
              <RefreshBoardTable boards={boards} names={names} />
            </details>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            Fetching boards costs nothing per call. What they use is the refresh&apos;s time, against Vercel&apos;s 300-second
            limit, and database space, against Supabase&apos;s 500 MB free plan.
          </p>
        </>
      )}
    </SectionCard>
  );
}

const SLOWEST_BOARDS = 15;

/** One row per board: fetch times, failures, jobs, embeddings and the space its saved jobs take. */
function RefreshBoardTable({ boards, names }: { boards: AdminStats["refresh_boards"]; names: Map<string, string> }) {
  return (
    <Table className="mt-1">
      <TableHeader>
        <TableRow>
          <TableHead>Company</TableHead>
          <TableHead>Board</TableHead>
          <TableHead className="text-right">Median</TableHead>
          <TableHead className="text-right">Last</TableHead>
          <TableHead className="text-right">Failed</TableHead>
          <TableHead className="text-right">Open jobs</TableHead>
          <TableHead className="text-right">Embedded</TableHead>
          <TableHead className="text-right">Saved jobs</TableHead>
          <TableHead className="text-right">Space</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {boards.map((row) => (
          <TableRow key={row.board}>
            <TableCell>{names.get(row.board) ?? "–"}</TableCell>
            <TableCell className="max-w-56 truncate font-mono text-xs" title={row.board}>
              {row.board}
            </TableCell>
            <TableCell className="text-right tabular-nums">{row.median_ms === null ? "–" : seconds(row.median_ms)}</TableCell>
            <TableCell className={cn("text-right tabular-nums", row.last_outcome !== null && row.last_outcome !== "ok" && "text-destructive")}>
              {row.last_ms === null ? "–" : row.last_outcome === "ok" ? seconds(row.last_ms) : row.last_outcome}
            </TableCell>
            <TableCell className={cn("text-right tabular-nums", row.failures > 0 && "text-destructive")}>{row.failures}</TableCell>
            <TableCell className="text-right tabular-nums">{row.open_jobs.toLocaleString()}</TableCell>
            <TableCell className={cn("text-right tabular-nums", row.embedded < row.open_jobs && "text-amber-600 dark:text-amber-400")}>
              {row.embedded.toLocaleString()}
            </TableCell>
            <TableCell className="text-right tabular-nums">{row.saved_jobs.toLocaleString()}</TableCell>
            <TableCell className="text-right tabular-nums">{size(row.bytes)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

const STEP_NAMES: Record<string, string> = {
  scoring: "Scoring",
  shortlist: "Title shortlist",
  titles: "Related titles",
  discovery: "Finding companies",
  naming: "Labeling companies",
  hacker_news: "Hacker News posts",
  gap_analysis: "Gap analysis",
  follow_up: "Follow-up drafts",
  other: "Other",
};

/** "84%", or "–" when there is nothing to divide by. */
function share(part: number, whole: number): string {
  return whole ? PERCENT.format(part / whole) : "–";
}

/** One line for an evaluation run's results, from the numbers each eval saves. */
function evalSummary(run: AdminStats["evals"][number]): string {
  const metrics = run.metrics as {
    skipped?: string;
    held_out?: number;
    arms?: Record<string, { auc: number }>;
    methods?: Record<string, { passing: number; scored: number }>;
    cut?: number;
  };
  if (metrics.skipped) return `Skipped: ${metrics.skipped}`;
  if (metrics.arms) {
    const arms = Object.entries(metrics.arms).map(([name, arm]) => `${name} AUC ${arm.auc.toFixed(2)}`);
    return `${metrics.held_out} held-out jobs · ${arms.join(" · ")}`;
  }
  if (metrics.methods) {
    const methods = Object.entries(metrics.methods).map(([name, method]) => `${name} ${method.passing} of ${method.scored}`);
    return `Reaching ${metrics.cut}: ${methods.join(" · ")}`;
  }
  return "–";
}

/**
 * The AI's quality and cost over time: prompt versions in use, fit scores checked against ratings per version, weekly
 * trends for drift, and the latest evaluation runs.
 */
function ModelQualitySection({ stats }: { stats: AdminStats }) {
  return (
    <SectionCard
      title="Model quality"
      description="Each prompt gets a version from its text, so a change to a prompt or model shows up as a new row. Weeks start on Monday, in UTC."
    >
      <p className="text-sm font-medium">Prompt versions</p>
      {stats.prompt_versions.length === 0 ? (
        <p className="mt-1 text-sm text-muted-foreground">No versioned calls yet. Calls record their prompt version from now on.</p>
      ) : (
        <Table className="mt-1">
          <TableHeader>
            <TableRow>
              <TableHead>Step</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Calls</TableHead>
              <TableHead className="text-right">First used</TableHead>
              <TableHead className="text-right">Last used</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {stats.prompt_versions.map((row) => (
              <TableRow key={`${row.step}-${row.prompt_version}-${row.model}`}>
                <TableCell>{STEP_NAMES[row.step] ?? row.step}</TableCell>
                <TableCell className="font-mono text-xs">{row.prompt_version ?? "before versions"}</TableCell>
                <TableCell className="font-mono text-xs">{row.model}</TableCell>
                <TableCell className="text-right tabular-nums">{row.calls.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{row.first.slice(0, 10)}</TableCell>
                <TableCell className="text-right tabular-nums">{row.last.slice(0, 10)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <p className="mt-6 text-sm font-medium">Fit scores by version</p>
      {stats.score_versions.length === 0 ? (
        <p className="mt-1 text-sm text-muted-foreground">No scores yet.</p>
      ) : (
        <Table className="mt-1">
          <TableHeader>
            <TableRow>
              <TableHead>Version</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Scored</TableHead>
              <TableHead className="text-right">Average</TableHead>
              <TableHead className="text-right">Rated</TableHead>
              <TableHead className="text-right">Rated good</TableHead>
              <TableHead className="text-right">70+ that were good</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {stats.score_versions.map((row) => (
              <TableRow key={`${row.prompt_version}-${row.model}`}>
                <TableCell className="font-mono text-xs">{row.prompt_version ?? "before versions"}</TableCell>
                <TableCell className="font-mono text-xs">{row.model ?? "–"}</TableCell>
                <TableCell className="text-right tabular-nums">{row.scored.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{Math.round(row.average_score)}</TableCell>
                <TableCell className="text-right tabular-nums">{row.rated}</TableCell>
                <TableCell className="text-right tabular-nums">{share(row.good, row.rated)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {share(row.predicted_good_correct, row.predicted_good)}
                  {row.predicted_good > 0 && <span className="text-muted-foreground"> of {row.predicted_good}</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <p className="mt-6 text-sm font-medium">Week by week</p>
      {stats.model_weeks.length === 0 ? (
        <p className="mt-1 text-sm text-muted-foreground">No calls or scores yet.</p>
      ) : (
        <Table className="mt-1">
          <TableHeader>
            <TableRow>
              <TableHead>Week of</TableHead>
              <TableHead className="text-right">Searches</TableHead>
              <TableHead className="text-right">Cost per search</TableHead>
              <TableHead className="text-right">Calls</TableHead>
              <TableHead className="text-right">Failed or cut off</TableHead>
              <TableHead className="text-right">Median time</TableHead>
              <TableHead className="text-right">Cache hits</TableHead>
              <TableHead className="text-right">Average score</TableHead>
              <TableHead className="text-right">Rated good</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {stats.model_weeks.map((row) => {
              const usage: RunUsage = {
                input_tokens: row.search_usage.input_tokens ?? 0,
                output_tokens: row.search_usage.output_tokens ?? 0,
                cache_read_input_tokens: row.search_usage.cache_read_input_tokens ?? 0,
                cache_creation_input_tokens: row.search_usage.cache_creation_input_tokens ?? 0,
                web_search_requests: row.search_usage.web_search_requests ?? 0,
              };
              const problems = row.errors + row.broken;
              return (
                <TableRow key={row.week}>
                  <TableCell className="tabular-nums">{row.week}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.searches}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.searches ? DOLLARS.format(runCost(usage) / row.searches) : "–"}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.calls.toLocaleString()}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", problems > 0 && "text-destructive")}>{share(problems, row.calls)}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.median_ms === null ? "–" : seconds(row.median_ms)}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.cache_share === null ? "–" : PERCENT.format(row.cache_share)}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.average_score === null ? "–" : Math.round(row.average_score)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {share(row.good, row.rated)}
                    {row.rated > 0 && <span className="text-muted-foreground"> of {row.rated}</span>}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      <p className="mt-6 text-sm font-medium">Evaluation runs</p>
      {stats.evals.length === 0 ? (
        <p className="mt-1 text-sm text-muted-foreground">No evaluation runs yet. They run every Monday, or by hand from the Evals workflow.</p>
      ) : (
        <Table className="mt-1">
          <TableHeader>
            <TableRow>
              <TableHead>Ran</TableHead>
              <TableHead>Eval</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Result</TableHead>
              <TableHead className="text-right">Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {stats.evals.map((run) => (
              <TableRow key={`${run.eval}-${run.created_at}`}>
                <TableCell className="tabular-nums">{utcTime(run.created_at)}</TableCell>
                <TableCell>{run.eval === "labels" ? "Scoring vs. ratings" : run.eval === "ranking" ? "Picking jobs to score" : run.eval}</TableCell>
                <TableCell className="font-mono text-xs">{run.prompt_version ?? "–"}</TableCell>
                <TableCell className="max-w-96 whitespace-normal text-xs">{evalSummary(run)}</TableCell>
                <TableCell className="text-right tabular-nums">{run.cost === null ? "–" : DOLLARS.format(Number(run.cost))}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </SectionCard>
  );
}
