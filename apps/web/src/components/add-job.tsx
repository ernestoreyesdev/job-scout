"use client";

import { ChevronDown, Plus } from "lucide-react";
import { useState, useTransition } from "react";

import { addOutsideJob } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { OUTSIDE_STATUSES } from "@/lib/db";

const FIELD = "h-9 w-full rounded-md border bg-transparent px-3 text-sm shadow-xs";

/**
 * Adds a job applied to outside the app by its link. After a link fails, it also asks for the title, company and
 * description, for jobs on sites the app can't read.
 */
export function AddJob() {
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [needsDetails, setNeedsDetails] = useState(false);
  const [pending, startTransition] = useTransition();

  function submit(formData: FormData) {
    startTransition(async () => {
      const result = await addOutsideJob(formData);
      setError(result.ok ? null : (result.error ?? "Could not add the job."));
      setMessage(result.ok ? (result.message ?? null) : null);
      setNeedsDetails(!result.ok);
    });
  }

  return (
    <details className="group mb-6 rounded-xl border bg-card px-4 py-3 text-sm shadow-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium select-none">
        <Plus className="size-4 text-muted-foreground" />
        Add a job you applied to
        <ChevronDown className="ml-auto size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <form action={submit} className="mt-3 space-y-3">
        <div className="space-y-1">
          <Label htmlFor="url" className="font-normal text-muted-foreground">
            The job&apos;s link, from the company&apos;s careers page or job board.
          </Label>
          <Input id="url" name="url" type="url" required placeholder="https://jobs.ashbyhq.com/ramp/…" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="status" className="font-normal text-muted-foreground">
              Status
            </Label>
            <select id="status" name="status" defaultValue="applied" className={FIELD}>
              {OUTSIDE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="applied_on" className="font-normal text-muted-foreground">
              Date applied, or leave empty for today
            </Label>
            <Input id="applied_on" name="applied_on" type="date" />
          </div>
        </div>
        {needsDetails && (
          <div className="space-y-3 rounded-lg border border-dashed p-3">
            <p className="text-muted-foreground">
              If the app can&apos;t read the link, enter the job yourself. A description lets it score the job against
              your resume.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Input name="title" placeholder="Job title" aria-label="Job title" />
              <Input name="company" placeholder="Company" aria-label="Company" />
            </div>
            <Textarea name="description" rows={4} placeholder="Job description (optional)" aria-label="Job description" />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="sm" disabled={pending}>
            <Plus />
            {pending ? "Adding…" : "Add to Jobs"}
          </Button>
          {error && <span className="text-destructive">{error}</span>}
          {message && <span className="text-muted-foreground">{message}</span>}
        </div>
      </form>
    </details>
  );
}
