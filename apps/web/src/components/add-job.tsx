"use client";

import { ChevronDown, CircleAlert, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { addOutsideJob, type AddJobResult } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { OUTSIDE_STATUSES, STATUS_LABELS } from "@/lib/db";
import { useAction } from "@/lib/use-action";

const FIELD = "h-9 w-full rounded-md border bg-transparent px-3 text-sm shadow-xs";
const LABEL = "font-normal text-muted-foreground";

/**
 * Adds a job applied to outside the app in two steps: its link first, then, only when the app can't read the link,
 * the job's title, company and description. What was typed stays until the job is added.
 */
export function AddJob() {
  const { run, pending, error } = useAction();
  const [last, setLast] = useState<AddJobResult | null>(null);
  const [needsDetails, setNeedsDetails] = useState(false);
  const message = last?.ok ? (last.message ?? null) : null;
  const unreadLink = last?.ok === false && !!last.needsDetails;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    run(() => addOutsideJob(new FormData(form)), "Could not add the job.", (result) => {
      setLast(result);
      if (result.ok) {
        form.reset();
        setNeedsDetails(false);
      } else if (result.needsDetails) {
        setNeedsDetails(true);
      }
    });
  }

  return (
    <details className="group mb-6 rounded-xl border bg-card px-4 py-3 text-sm shadow-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium select-none">
        <Plus className="size-4 text-muted-foreground" />
        Add a job you applied to
        <ChevronDown className="ml-auto size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <form onSubmit={submit} className="mt-3 space-y-4">
        <div className="space-y-1">
          <Label htmlFor="url" className={LABEL}>
            Job link <span className="text-destructive">*</span>
          </Label>
          <div className="flex items-center gap-3">
            <Input
              id="url"
              name="url"
              type="url"
              required
              readOnly={needsDetails}
              placeholder="https://jobs.ashbyhq.com/ramp/…"
              className={needsDetails ? "text-muted-foreground" : undefined}
            />
            {needsDetails && (
              <Button type="button" variant="link" size="sm" className="px-0" onClick={() => setNeedsDetails(false)}>
                Change
              </Button>
            )}
          </div>
        </div>
        {needsDetails && (
          <div className="space-y-3">
            <p className="flex items-start gap-2 rounded-md bg-amber-100 px-3 py-2 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
              We couldn&apos;t read this link. Enter the job&apos;s details and we&apos;ll save them with the link.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="title" className={LABEL}>
                  Job title <span className="text-destructive">*</span>
                </Label>
                <Input id="title" name="title" required placeholder="Senior Backend Engineer" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="company" className={LABEL}>
                  Company <span className="text-destructive">*</span>
                </Label>
                <Input id="company" name="company" required placeholder="Acme" />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="description" className={LABEL}>
                Job description <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="description"
                name="description"
                required
                rows={5}
                placeholder="Paste the full description. Your fit score comes from it."
              />
            </div>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="status" className={LABEL}>
              Status
            </Label>
            <select id="status" name="status" defaultValue="applied" className={FIELD}>
              {OUTSIDE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="applied_on" className={LABEL}>
              Date applied, or leave empty for today
            </Label>
            <Input id="applied_on" name="applied_on" type="date" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="sm" disabled={pending}>
            <Plus />
            {pending ? "Adding…" : "Add to Jobs"}
          </Button>
          {error && !unreadLink && <span className="text-destructive">{error}</span>}
          {message && <span className="text-muted-foreground">{message}</span>}
        </div>
      </form>
    </details>
  );
}
