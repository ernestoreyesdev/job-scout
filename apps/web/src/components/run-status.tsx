"use client";

import { CircleAlert, CircleCheck, CircleStop, LoaderCircle, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { rerunSearch, rescoreJobs, stopRun } from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { AgentRunRow, RunStatusRow, SearchRuleInput } from "@/lib/db";
import { describeRun } from "@/lib/runs";
import { cn } from "@/lib/utils";

const REFRESH_MS = 3000;

/**
 * Latest search run; refreshes the page while the run is still working, offers to stop it meanwhile, and offers a
 * re-run once it failed or was stopped.
 */
export function RunStatus({ run }: { run: AgentRunRow }) {
  const router = useRouter();
  const active = run.status === "queued" || run.status === "running";
  const [rerunError, setRerunError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function rerun(webLookup: boolean) {
    startTransition(async () => {
      const result = run.kind === "rescore" ? await rescoreJobs() : await rerunSearch(run.id, webLookup);
      setRerunError(result.ok ? null : (result.error ?? "Could not re-run the search."));
    });
  }

  function stop() {
    startTransition(async () => {
      const result = await stopRun(run.id);
      setRerunError(result.ok ? null : (result.error ?? "Could not stop the search."));
    });
  }

  // Polls the agent's progress, which lives outside React, until the run finishes.
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [active, router]);

  const input = run.input as Partial<SearchRuleInput>;
  const offerWebLookup = run.error_code === "company_not_found" && !!input.company && !input.web_lookup;
  const ended = run.status === "failed" || run.status === "stopped";
  const { title, detail } = describeRun(run);

  const { Icon, tone } = STATUS_LOOK[run.status];

  return (
    <div className={cn("mt-4 flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 text-sm", tone)}>
      <Icon className={cn("size-4 shrink-0", active && "animate-spin")} aria-label={run.status} />
      <div className="min-w-0 flex-1">
        <p className="truncate" title={`${title}${detail}`}>
          <span className="font-medium">{title}</span>
          <span className="opacity-80">{detail}</span>
        </p>
        {(run.progress || run.error) && (
          <p className={cn("truncate opacity-80", run.error && "text-destructive opacity-100")} title={run.error ?? run.progress ?? undefined}>
            {run.error ?? run.progress}
          </p>
        )}
        {rerunError && <p className="text-destructive">{rerunError}</p>}
      </div>
      {active && (
        <Button variant="outline" size="sm" className="rounded-full bg-background" onClick={stop} disabled={pending}>
          {pending ? "Stopping…" : "Stop"}
        </Button>
      )}
      {ended && (run.kind === "search" || run.kind === "rescore") && (
        <Button
          variant="outline"
          size="sm"
          className="rounded-full bg-background"
          onClick={() => rerun(offerWebLookup)}
          disabled={pending}
        >
          {pending ? "Starting…" : offerWebLookup ? `Search the web for ${input.company}` : "Re-run"}
        </Button>
      )}
    </div>
  );
}

const STATUS_LOOK: Record<RunStatusRow, { Icon: LucideIcon; tone: string }> = {
  queued: { Icon: LoaderCircle, tone: "bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100" },
  running: { Icon: LoaderCircle, tone: "bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100" },
  done: { Icon: CircleCheck, tone: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100" },
  failed: { Icon: CircleAlert, tone: "border border-destructive/30 bg-destructive/5" },
  stopped: { Icon: CircleStop, tone: "bg-muted text-foreground" },
};
