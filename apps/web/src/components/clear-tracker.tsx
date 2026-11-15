"use client";

import { useState } from "react";

import { clearTracker } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { useAction } from "@/lib/use-action";

/** Two-step Clear: the first click asks, the second empties the Tracker. */
export function ClearTracker({ count }: { count: number }) {
  const [confirming, setConfirming] = useState(false);
  const { run, pending, error } = useAction();

  function clear() {
    run(clearTracker, "Could not clear the Tracker.", () => setConfirming(false));
  }

  if (!confirming) {
    return (
      <div className="flex items-center gap-3">
        {error && <span className="text-sm text-destructive">{error}</span>}
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => setConfirming(true)}>
          Clear tracker
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">
        Clear {count} {count === 1 ? "job" : "jobs"}? They&apos;re deleted.
      </span>
      <Button variant="destructive" size="sm" onClick={clear} disabled={pending}>
        {pending ? "Clearing…" : "Clear"}
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setConfirming(false)} disabled={pending}>
        Cancel
      </Button>
    </div>
  );
}
