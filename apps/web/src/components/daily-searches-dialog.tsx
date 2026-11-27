"use client";

import { setSearchAlert, type DailySearch } from "@/app/actions";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { DAILY_SEARCH_CHOICES } from "@/lib/db";
import { useAction } from "@/lib/use-action";

/**
 * Picks which searches run each morning: the latest DAILY_SEARCH_CHOICES from the Tracker, then older checked ones
 * under "Older". `searches` is null when they couldn't load, and `onChange` gets the list on each pick, then the
 * earlier one back if saving fails. A note says when emails are paused, or on with nothing picked.
 */
export function DailySearchesDialog({
  open,
  onOpenChange,
  emailsOn,
  searches,
  loadError,
  onChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  emailsOn: boolean;
  searches: DailySearch[] | null;
  loadError: string | null;
  onChange: (searches: DailySearch[]) => void;
}) {
  const { run, pending, error } = useAction();

  function pick(index: number, on: boolean) {
    if (!searches) return;
    onChange(searches.map((search, i) => (i === index ? { ...search, on } : search)));
    run(() => setSearchAlert(searches[index], on), "Could not update this search.", (result) => !result.ok && onChange(searches));
  }

  const picked = searches?.some((search) => search.on) ?? false;
  const note = !emailsOn
    ? "Emails are paused. Turn on Daily match emails in the account menu to get them."
    : searches && !picked
      ? "Pick at least one search to get daily emails."
      : null;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Choose daily searches</AlertDialogTitle>
          <AlertDialogDescription>
            Your last {DAILY_SEARCH_CHOICES} searches from the Tracker. Checked ones run each morning after the boards
            refresh, and you get one email with the 10 best new matches.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {note && <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">{note}</p>}
        {searches?.length === 0 && (
          <p className="text-sm text-muted-foreground">Run a search from the Tracker first, then pick it here.</p>
        )}
        {searches && searches.length > 0 && (
          <ul className="divide-y rounded-lg border text-sm">
            {searches.map((search, index) => (
              <li key={search.runId ?? search.alertId}>
                {!search.runId && searches[index - 1]?.runId !== null && (
                  <p className="border-b bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">Older</p>
                )}
                <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-4 shrink-0 accent-foreground"
                    checked={search.on}
                    disabled={pending}
                    onChange={(event) => pick(index, event.target.checked)}
                  />
                  <span className="min-w-0">
                    <span className="font-medium">{search.title}</span>
                    {search.detail && <span className="block text-muted-foreground">{search.detail.replace(/^ · /, "")}</span>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        {(loadError ?? error) && <p className="text-sm text-destructive">{loadError ?? error}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel>Done</AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
