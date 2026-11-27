"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { rescoreJobs } from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { RescoreScope } from "@/lib/db";
import { useAction } from "@/lib/use-action";

/** Starts a run that scores this page's jobs scored against an older resume or not scored yet. */
export function RescoreButton({ count, scope }: { count: number; scope: RescoreScope }) {
  const [started, setStarted] = useState(false);
  const { run, pending, error } = useAction();

  function rescore() {
    run(() => rescoreJobs(scope), "Could not start.", (result) => setStarted(result.ok));
  }

  const message = error ?? (started ? "Scoring started." : null);

  return (
    <div className="flex items-center gap-3 text-sm">
      {message && <span className="text-muted-foreground">{message}</span>}
      <Button variant="outline" size="sm" onClick={rescore} disabled={pending}>
        <RefreshCw />
        {pending ? "Starting…" : `Score ${count} with current resume`}
      </Button>
    </div>
  );
}
