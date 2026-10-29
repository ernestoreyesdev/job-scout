"use client";

import { EyeOff, Trash2 } from "lucide-react";
import { useState, useTransition } from "react";

import { deleteApplication, removeFromTracker, updateApplication } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TableCell, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { APPLICATION_STATUSES, type TrackedJob } from "@/lib/db";

/**
 * One tracked job: position, score, posting link, status select, optional notes saved on blur, and actions.
 * Delete removes the job everywhere; remove (Tracker only, jobs past "new") keeps it under Jobs.
 */
export function JobRow({
  job,
  position,
  showNotes,
  canRemoveFromTracker,
}: {
  job: TrackedJob;
  position: number;
  showNotes: boolean;
  canRemoveFromTracker: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
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
        {job.fit_summary && <p className="mt-1 text-sm text-muted-foreground">{job.fit_summary}</p>}
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
