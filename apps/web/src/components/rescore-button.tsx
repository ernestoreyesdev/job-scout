"use client";

import { RefreshCw } from "lucide-react";
import { useState, useTransition } from "react";

import { rescoreJobs } from "@/app/actions";
import { Button } from "@/components/ui/button";

/** Starts a run that re-scores the jobs scored against an older resume. */
export function RescoreButton({ count }: { count: number }) {
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function rescore() {
    startTransition(async () => {
      const result = await rescoreJobs();
      setMessage(result.ok ? "Re-scoring started. Progress shows on the Tracker." : (result.error ?? "Could not start."));
    });
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      {message && <span className="text-muted-foreground">{message}</span>}
      <Button variant="outline" size="sm" onClick={rescore} disabled={pending}>
        <RefreshCw />
        {pending ? "Starting…" : `Re-score ${count} with current resume`}
      </Button>
    </div>
  );
}
