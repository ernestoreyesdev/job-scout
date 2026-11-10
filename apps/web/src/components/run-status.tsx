"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { rerunSearch, rescoreJobs, stopRun } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AgentRunRow, SearchRuleInput } from "@/lib/db";
import { describeRun } from "@/lib/runs";

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

  return (
    <div className="mt-6 flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-sm">
      <Badge
        variant={
          run.status === "failed" ? "destructive" : run.status === "stopped" ? "outline" : active ? "secondary" : "default"
        }
      >
        {run.status}
      </Badge>
      <span>
        <span className="font-medium">{title}</span>
        {detail}
      </span>
      {run.progress && (
        <span className="ml-auto min-w-0 truncate text-muted-foreground" title={run.progress}>
          {run.progress}
        </span>
      )}
      {active && (
        <Button
          variant="outline"
          size="sm"
          className={run.progress ? undefined : "ml-auto"}
          onClick={stop}
          disabled={pending}
        >
          {pending ? "Stopping…" : "Stop"}
        </Button>
      )}
      {ended && (run.kind === "search" || run.kind === "rescore") && (
        <Button
          variant="outline"
          size="sm"
          className={run.progress ? undefined : "ml-auto"}
          onClick={() => rerun(offerWebLookup)}
          disabled={pending}
        >
          {pending ? "Starting…" : offerWebLookup ? `Search the web for ${input.company}` : "Re-run"}
        </Button>
      )}
      {run.error && <span className="w-full text-destructive">{run.error}</span>}
      {rerunError && <span className="w-full text-destructive">{rerunError}</span>}
    </div>
  );
}
