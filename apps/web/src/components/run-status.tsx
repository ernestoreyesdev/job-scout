"use client";

import { CircleAlert, CircleCheck, CircleStop, LoaderCircle, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { readRun, rerunSearch, rescoreJobs, stopRun } from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { RunSummary, RunStatusRow, SearchRuleInput } from "@/lib/db";
import { describeRun, rescoreScope } from "@/lib/runs";
import { useAction } from "@/lib/use-action";
import { cn } from "@/lib/utils";

const REFRESH_MS = 3000;
const STATUS_LOOK: Record<RunStatusRow, { Icon: LucideIcon; tone: string }> = {
  queued: { Icon: LoaderCircle, tone: "bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100" },
  running: { Icon: LoaderCircle, tone: "bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100" },
  done: { Icon: CircleCheck, tone: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100" },
  failed: { Icon: CircleAlert, tone: "border border-destructive/30 bg-destructive/5" },
  stopped: { Icon: CircleStop, tone: "bg-muted text-foreground" },
};

/**
 * Latest search run; while it works, reads just the run every REFRESH_MS and reloads the page once it ends. Offers to
 * stop it meanwhile, and a re-run once it failed or was stopped.
 */
export function RunStatus({ run: loaded }: { run: RunSummary }) {
  const router = useRouter();
  const [polled, setPolled] = useState<RunSummary | null>(null);
  const run = polled?.id === loaded.id && polled.updated_at > loaded.updated_at ? polled : loaded;
  const active = run.status === "queued" || run.status === "running";
  const { run: act, pending, error: rerunError } = useAction();

  function rerun(webLookup: boolean) {
    act(() => (run.kind === "rescore" ? rescoreJobs(rescoreScope(run)) : rerunSearch(run.id, webLookup)), "Could not re-run the search.");
  }

  function stop() {
    act(() => stopRun(run.id), "Could not stop the search.");
  }

  // Polls the agent's progress, which lives outside React, until the run finishes.
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(async () => {
      const result = await readRun(loaded.id);
      if (!result.run) return;
      setPolled(result.run);
      if (result.run.status !== "queued" && result.run.status !== "running") router.refresh();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [active, loaded.id, router]);

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
