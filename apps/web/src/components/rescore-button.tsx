"use client";

import { RefreshCw } from "lucide-react";
import { useState, useTransition } from "react";

import { rescoreJobs } from "@/app/actions";
import { Button } from "@/components/ui/button";
import type { RescoreScope } from "@/lib/db";

/** Starts a run that scores this page's jobs scored against an older resume or not scored yet. */
export function RescoreButton({ count, scope }: { count: number; scope: RescoreScope }) {
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function rescore() {
    startTransition(async () => {
      const result = await rescoreJobs(scope);
      setMessage(result.ok ? "Scoring started." : (result.error ?? "Could not start."));
    });
  }

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
