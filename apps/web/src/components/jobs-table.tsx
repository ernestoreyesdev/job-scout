"use client";

import Link from "next/link";
import { useState } from "react";

import { JobRow } from "@/components/job-row";
import { RATED_PATH, type TrackedJob } from "@/lib/db";
import { ISO_DAY } from "@/lib/format";

/**
 * The jobs on one page of the Tracker or Jobs, one card each. On the Tracker's new jobs, a job moved past new or
 * rated leaves the list, and a note above it says where it went.
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
  const [moved, setMoved] = useState<{ title: string; to: "jobs" | "rated" } | null>(null);

  return (
    <>
      {moved && (
        <p role="status" className="mb-3 flex flex-wrap items-center gap-x-3 rounded-lg bg-muted/60 px-3 py-2 text-sm">
          <span>
            {moved.title} moved to {moved.to === "rated" ? "Rated" : "Jobs"}.
          </span>
          <Link href={moved.to === "rated" ? RATED_PATH : "/jobs"} className="font-medium underline">
            {moved.to === "rated" ? "Open Rated" : "Open Jobs"}
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
            onLeftTracker={onTracker ? (to) => setMoved({ title: job.posting.title, to }) : undefined}
            staleResume={currentResumeId !== null && job.fit_score !== null && job.resume_id !== currentResumeId}
            closedOn={job.posting.closed_at ? ISO_DAY.format(new Date(job.posting.closed_at)) : null}
            timeline={job.events.map((event) => `${event.status === "new" ? "added" : event.status} ${ISO_DAY.format(new Date(event.changed_at))}`)}
          />
        ))}
      </ul>
    </>
  );
}
