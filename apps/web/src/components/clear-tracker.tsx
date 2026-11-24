"use client";

import { useState } from "react";

import { clearTracker } from "@/app/actions";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useAction } from "@/lib/use-action";

/** Clear tracker button that asks in a dialog before emptying the Tracker. */
export function ClearTracker({ count }: { count: number }) {
  const [confirming, setConfirming] = useState(false);
  const { run, pending, error } = useAction();

  function clear() {
    run(clearTracker, "Could not clear the Tracker.", (result) => setConfirming(!result.ok));
  }

  return (
    <>
      <Button variant="outline" size="sm" className="rounded-full" onClick={() => setConfirming(true)}>
        Clear tracker
      </Button>
      <AlertDialog open={confirming} onOpenChange={(open) => !pending && setConfirming(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear the Tracker?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes its {count} {count === 1 ? "job" : "jobs"}.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
            <Button variant="destructive" onClick={clear} disabled={pending}>
              {pending ? "Clearing…" : "Clear"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
