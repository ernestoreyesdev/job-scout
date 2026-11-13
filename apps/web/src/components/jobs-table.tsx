"use client";

import Link from "next/link";
import { useState } from "react";

import { JobRow } from "@/components/job-row";
import type { TrackedJob } from "@/lib/db";

// Swedish formatting is ISO: "2026-11-13".
const DAY = new Intl.DateTimeFormat("sv-SE", { year: "numeric", month: "2-digit", day: "2-digit" });

/**
 * The jobs on one page of the Tracker or Jobs, one card each. On the Tracker, a job moved past new or rated leaves
 * the list, and a note above it says where it went.
 */
export function JobsTable({
  jobs,
  showNotes,
  onTracker,
  currentResumeId,
}: {
  jobs: TrackedJob[];
  showNotes: boolean;
  onTracker: boolean;
  currentResumeId: string | null;
}) {
  const [moved, setMoved] = useState<{ title: string; rated: boolean } | null>(null);

  return (
    <>
      {moved && (
        <p role="status" className="mb-3 flex flex-wrap items-center gap-x-3 rounded-lg bg-muted/60 px-3 py-2 text-sm">
          <span>
            {moved.title} moved to Jobs{moved.rated && ", under Rated"}.
          </span>
          <Link href={moved.rated ? "/jobs?view=rated" : "/jobs"} className="font-medium underline">
            {moved.rated ? "Open Rated" : "Open Jobs"}
          </Link>
          <button type="button" onClick={() => setMoved(null)} className="ml-auto text-muted-foreground hover:text-foreground">
            Dismiss
          </button>
        </p>
      )}
      <ul className="space-y-3">
        {jobs.map((job) => (
          <JobRow
            key={job.id}
            job={job}
            showNotes={showNotes}
            onMovedToJobs={onTracker ? (rated) => setMoved({ title: job.posting.title, rated }) : undefined}
            staleResume={currentResumeId !== null && job.resume_id !== null && job.resume_id !== currentResumeId}
            closedOn={job.posting.closed_at ? DAY.format(new Date(job.posting.closed_at)) : null}
            timeline={job.events.map((event) => `${event.status === "new" ? "added" : event.status} ${DAY.format(new Date(event.changed_at))}`)}
          />
        ))}
      </ul>
    </>
  );
}
