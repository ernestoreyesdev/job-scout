import { Suspense } from "react";

import { AccuracyTable } from "@/components/accuracy-table";
import { KeyForm } from "@/components/key-form";
import { SectionCard } from "@/components/section-card";
import { StatTile } from "@/components/stat-tile";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { callAgent } from "@/lib/agent";
import type { AgentRunRow, ApplicationStatusRow, CompanyKindRow, FitLabelRow } from "@/lib/db";
import { MIN_LABELED, accuracyByCut, runCost, summarizeCosts } from "@/lib/insights";
import { getAdminSource } from "@/lib/repository";

const DOLLARS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const DAY_MS = 24 * 60 * 60 * 1000;
const ACTIVE_DAYS = 7;
const CHART_DAYS = 14;

type AdminStats = {
  generated_at: string;
  days: number;
  users: { id: string; email: string | null; created_at: string | null; last_sign_in_at: string | null }[];
  runs: Pick<AgentRunRow, "user_id" | "kind" | "status" | "created_at" | "usage">[];
  companies: { source: string; kind: CompanyKindRow | null; open_jobs: number }[];
  labels: { fit_score: number | null; fit_label: FitLabelRow | null }[];
  applications: { user_id: string; status: ApplicationStatusRow }[];
};

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
