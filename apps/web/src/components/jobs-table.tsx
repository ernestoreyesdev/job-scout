import { JobRow } from "@/components/job-row";
import type { TrackedJob } from "@/lib/db";

const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

/** The jobs on one page of the Tracker or Jobs, one card each. */
export function JobsTable({
  jobs,
  showNotes,
  canRemoveFromTracker,
  currentResumeId,
}: {
  jobs: TrackedJob[];
  showNotes: boolean;
  canRemoveFromTracker: boolean;
  currentResumeId: string | null;
}) {
  return (
    <ul className="space-y-3">
      {jobs.map((job) => (
        <JobRow
          key={job.id}
          job={job}
          showNotes={showNotes}
          canRemoveFromTracker={canRemoveFromTracker}
          staleResume={currentResumeId !== null && job.resume_id !== null && job.resume_id !== currentResumeId}
          closedOn={job.posting.closed_at ? DAY.format(new Date(job.posting.closed_at)) : null}
          timeline={job.events.map((event) => `${event.status === "new" ? "added" : event.status} ${DAY.format(new Date(event.changed_at))}`)}
        />
      ))}
    </ul>
  );
}
