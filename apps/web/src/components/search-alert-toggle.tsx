"use client";

import { Bell, BellOff } from "lucide-react";

import { setSearchAlert } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { useAction } from "@/lib/use-action";

/** Turns a past search's daily run on or off: each morning it runs again and emails the new jobs scoring 70 or more. */
export function SearchAlertToggle({ runId, on }: { runId: string; on: boolean }) {
  const { run, pending, error } = useAction();

  return (
    <span className="block">
      <Button
        variant="ghost"
        size="sm"
        className="-ml-2 h-7 px-2 text-xs"
        onClick={() => run(() => setSearchAlert(runId, !on), "Could not update this search.")}
        disabled={pending}
        title="Runs this search each morning and emails you new jobs scoring 70 or more"
      >
        {on ? <Bell /> : <BellOff />}
        {on ? "Emailing new matches daily" : "Email me new matches"}
      </Button>
      {error && <span className="block text-destructive">{error}</span>}
    </span>
  );
}
