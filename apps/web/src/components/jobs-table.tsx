import { ArrowDown, ArrowUp } from "lucide-react";
import Link from "next/link";

import { JobRow } from "@/components/job-row";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { TrackedJob } from "@/lib/db";
import { jobListHref } from "@/lib/job-query";

const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

/**
 * Numbered jobs table with a Score header that flips the score sort through
 * `?sort=`, keeping the other list settings in `params`; numbering starts after `offset`.
 */
export function JobsTable({
  jobs,
  basePath,
  ascending,
  params,
  showNotes,
  canRemoveFromTracker,
  offset,
  currentResumeId,
}: {
  jobs: TrackedJob[];
  basePath: string;
  ascending: boolean;
  params: Record<string, string>;
  showNotes: boolean;
  canRemoveFromTracker: boolean;
  offset: number;
  currentResumeId: string | null;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-10">#</TableHead>
          <TableHead className="w-20">
            <Link
              href={jobListHref(basePath, { ...params, sort: ascending ? "" : "asc" })}
              className="inline-flex items-center gap-1 hover:text-foreground"
              aria-label={ascending ? "Sort by score, highest first" : "Sort by score, lowest first"}
            >
              Score
              {ascending ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />}
            </Link>
          </TableHead>
          <TableHead>Job</TableHead>
          <TableHead className="w-40">Status</TableHead>
          {showNotes && <TableHead className="w-72">Notes</TableHead>}
          <TableHead className="w-24">
            <span className="sr-only">Actions</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job, index) => (
          <JobRow
            key={job.id}
            job={job}
            position={offset + index + 1}
            showNotes={showNotes}
            canRemoveFromTracker={canRemoveFromTracker}
            staleResume={currentResumeId !== null && job.resume_id !== null && job.resume_id !== currentResumeId}
            closedOn={job.posting.closed_at ? DAY.format(new Date(job.posting.closed_at)) : null}
            timeline={job.events.map((event) => `${event.status === "new" ? "added" : event.status} ${DAY.format(new Date(event.changed_at))}`)}
          />
        ))}
      </TableBody>
    </Table>
  );
}
