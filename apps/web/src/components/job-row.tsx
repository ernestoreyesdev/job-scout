"use client";

import { ChevronDown, EyeOff, Trash2 } from "lucide-react";
import { useState, useTransition } from "react";

import { deleteApplication, removeFromTracker, updateApplication } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TableCell, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { APPLICATION_STATUSES, type TrackedJob } from "@/lib/db";
import { cn } from "@/lib/utils";

/**
 * One tracked job: position, score, posting link, status select, optional notes saved on blur, and actions.
 * Delete removes the job everywhere; remove (Tracker only, jobs past "new") keeps it under Jobs.
 */
export function JobRow({
  job,
  position,
  showNotes,
  canRemoveFromTracker,
  staleResume,
  closedOn,
  timeline,
}: {
  job: TrackedJob;
  position: number;
  showNotes: boolean;
  canRemoveFromTracker: boolean;
  staleResume: boolean;
  closedOn: string | null;
  timeline: string[];
}) {
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const hasDetails = job.strengths.length > 0 || job.gaps.length > 0 || timeline.length > 0;
  const [pending, startTransition] = useTransition();

  function save(field: "status" | "notes", value: string) {
    const formData = new FormData();
    formData.set(field, value);
    startTransition(async () => {
      const result = await updateApplication(job.id, formData);
      setError(result.ok ? null : (result.error ?? "Could not save."));
    });
  }

  function remove() {
    startTransition(async () => {
      const result = await deleteApplication(job.id);
      if (!result.ok) setError(result.error ?? "Could not delete.");
    });
  }

  function hide() {
    startTransition(async () => {
      const result = await removeFromTracker(job.id);
      if (!result.ok) setError(result.error ?? "Could not remove from the Tracker.");
    });
  }

  return (
    <TableRow className="align-top">
      <TableCell className="text-muted-foreground tabular-nums">{position}</TableCell>
      <TableCell className="text-lg font-semibold tabular-nums">{job.fit_score ?? "–"}</TableCell>
      <TableCell className="whitespace-normal">
        <a href={job.posting.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
          {job.posting.title}
        </a>
        <div className="text-xs text-muted-foreground">
          {job.posting.company}
          {job.posting.location ? ` · ${job.posting.location}` : ""}
        </div>
        {closedOn && (
          <p className="mt-1 text-xs font-medium text-destructive">Closed: no longer listed since {closedOn}</p>
        )}
        {job.fit_summary && <p className="mt-1 text-sm text-muted-foreground">{job.fit_summary}</p>}
        {staleResume && <p className="mt-1 text-xs text-amber-600">Scored with an older resume</p>}
        {hasDetails && (
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            aria-expanded={showDetails}
          >
            {showDetails ? "Hide details" : "Details"}
            <ChevronDown className={cn("size-3.5 transition-transform", showDetails && "rotate-180")} />
          </button>
        )}
        {showDetails && timeline.length > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">{timeline.join(" · ")}</p>
        )}
        {showDetails && (job.strengths.length > 0 || job.gaps.length > 0) && (
          <div className="mt-2 grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <p className="font-medium">Strengths</p>
              <ul className="mt-1 list-disc space-y-1 pl-4 text-muted-foreground">
                {job.strengths.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium">Gaps</p>
              <ul className="mt-1 list-disc space-y-1 pl-4 text-muted-foreground">
                {job.gaps.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        {error && <p className="mt-1 text-sm text-destructive">{error}</p>}
      </TableCell>
      <TableCell>
        <Select
          key={job.status}
          defaultValue={job.status}
          onValueChange={(value) => save("status", value)}
          disabled={pending}
        >
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {APPLICATION_STATUSES.map((status) => (
              <SelectItem key={status} value={status}>
                {status}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      {showNotes && (
        <TableCell>
          <Textarea
            defaultValue={job.notes ?? ""}
            placeholder="Notes"
            rows={2}
            onBlur={(event) => {
              if (event.target.value !== (job.notes ?? "")) save("notes", event.target.value);
            }}
          />
        </TableCell>
      )}
      <TableCell>
        <div className="flex justify-end gap-1">
          {canRemoveFromTracker && job.status !== "new" && (
            <Button
              variant="ghost"
              size="icon"
              onClick={hide}
              disabled={pending}
              title="Remove from Tracker (stays in Jobs)"
              aria-label={`Remove ${job.posting.title} from the Tracker, keeping it in Jobs`}
            >
              <EyeOff />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={remove}
            disabled={pending}
            title="Delete from Tracker and Jobs"
            aria-label={`Delete ${job.posting.title} from the Tracker and Jobs`}
          >
            <Trash2 />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}
