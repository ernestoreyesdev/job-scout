"use client";

import { ChevronDown, EyeOff, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { useState, useTransition } from "react";

import { analyzeGaps, deleteApplication, draftFollowUp, removeFromTracker, updateApplication } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TableCell, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  APPLICATION_STATUSES,
  FOLLOW_UP_DAYS,
  GHOST_JOB_DAYS,
  type FitLabelRow,
  type GapItem,
  type PostingRow,
  type TrackedJob,
} from "@/lib/db";
import { cn } from "@/lib/utils";

const PERIODS = { year: "yr", month: "mo", week: "wk", day: "day", hour: "hr" } as const;

const GAP_SECTIONS = [
  ["covered", "Covered"],
  ["weak", "Weak"],
  ["missing", "Missing"],
] as const;

/**
 * One tracked job: position, score, posting link, facts read from the posting, ghost-job and follow-up notes,
 * status select, optional notes saved on blur, and actions. Thumbs up or down records whether the user agrees it
 * fits; clicking the active one clears it. Details shows the timeline, strengths and gaps, and an on-demand gap
 * analysis. Delete removes the job everywhere; remove (Tracker only, jobs past "new") keeps it under Jobs.
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
  const [followUp, setFollowUp] = useState<{ subject: string; body: string } | null>(null);
  const [pending, startTransition] = useTransition();
  const { openDays, reposted, daysSinceApplied } = job.signals;
  const ghost = [
    openDays !== null && openDays >= GHOST_JOB_DAYS && `open ${openDays} days`,
    reposted && "reposted",
  ].filter(Boolean);

  const facts = postingFacts(job.posting);

  function save(field: "status" | "notes" | "fitLabel", value: string) {
    const formData = new FormData();
    formData.set(field, value);
    startTransition(async () => {
      const result = await updateApplication(job.id, formData);
      setError(result.ok ? null : (result.error ?? "Could not save."));
    });
  }

  function analyze() {
    startTransition(async () => {
      const result = await analyzeGaps(job.id);
      setError(result.ok ? null : (result.error ?? "Could not analyze this job."));
    });
  }

  function draft() {
    startTransition(async () => {
      const result = await draftFollowUp(job.id);
      setError(result.ok ? null : (result.error ?? "Could not draft a follow-up."));
      if (result.ok && result.subject !== undefined && result.body !== undefined) {
        setFollowUp({ subject: result.subject, body: result.body });
      }
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
        {facts.length > 0 && <div className="mt-1 text-xs text-muted-foreground">{facts.join(" · ")}</div>}
        {closedOn && (
          <p className="mt-1 text-xs font-medium text-destructive">Closed: no longer listed since {closedOn}</p>
        )}
        {job.fit_summary && <p className="mt-1 text-sm text-muted-foreground">{job.fit_summary}</p>}
        {staleResume && <p className="mt-1 text-xs text-amber-600">Scored with an older resume</p>}
        {ghost.length > 0 && <p className="mt-1 text-xs text-amber-600">Possible ghost job: {ghost.join(", ")}</p>}
        {daysSinceApplied !== null && daysSinceApplied >= FOLLOW_UP_DAYS && (
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-amber-600">No response in {daysSinceApplied} days</span>
            {!followUp && (
              <button type="button" onClick={draft} disabled={pending} className="underline hover:text-foreground">
                {pending ? "Drafting…" : "Draft follow-up"}
              </button>
            )}
          </div>
        )}
        {followUp && (
          <div className="mt-2 space-y-1 rounded-md border p-2 text-sm">
            <p className="font-medium">{followUp.subject}</p>
            <Textarea readOnly value={followUp.body} rows={6} />
            <div className="flex gap-3 text-xs">
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(`${followUp.subject}\n\n${followUp.body}`)}
                className="underline hover:text-foreground"
              >
                Copy
              </button>
              <button type="button" onClick={() => setFollowUp(null)} className="text-muted-foreground hover:text-foreground">
                Close
              </button>
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => setShowDetails(!showDetails)}
          className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          aria-expanded={showDetails}
        >
          {showDetails ? "Hide details" : "Details"}
          <ChevronDown className={cn("size-3.5 transition-transform", showDetails && "rotate-180")} />
        </button>
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
        {showDetails &&
          (job.gap_analysis ? (
            <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
              {GAP_SECTIONS.map(([key, title]) => (
                <GapList key={key} title={title} items={job.gap_analysis![key]} />
              ))}
            </div>
          ) : (
            <Button variant="outline" size="sm" className="mt-3" onClick={analyze} disabled={pending}>
              {pending ? "Analyzing…" : "Analyze gaps"}
            </Button>
          ))}
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
          {(["good", "bad"] as const satisfies readonly FitLabelRow[]).map((label) => {
            const active = job.fit_label === label;
            const Icon = label === "good" ? ThumbsUp : ThumbsDown;
            return (
              <Button
                key={label}
                variant="ghost"
                size="icon"
                onClick={() => save("fitLabel", active ? "" : label)}
                disabled={pending}
                aria-pressed={active}
                title={label === "good" ? "Good fit" : "Bad fit"}
                aria-label={`Mark ${job.posting.title} as a ${label} fit`}
                className={cn(active && (label === "good" ? "text-emerald-600" : "text-destructive"))}
              >
                <Icon className={cn(active && "fill-current")} />
              </Button>
            );
          })}
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

/** Short labels for the facts read from a posting: pay, clearance, visa sponsorship, experience and stack. */
function postingFacts(posting: PostingRow): string[] {
  const facts: string[] = [];
  if (posting.salary_min !== null || posting.salary_max !== null) {
    const money = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: posting.salary_currency ?? "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    });
    const low = posting.salary_min ?? posting.salary_max;
    const high = posting.salary_max ?? posting.salary_min;
    const range = low === high ? money.format(low!) : `${money.format(low!)}–${money.format(high!)}`;
    facts.push(posting.salary_period ? `${range}/${PERIODS[posting.salary_period]}` : range);
  }
  if (posting.clearance) facts.push(`Clearance: ${posting.clearance}`);
  if (posting.visa_sponsorship) facts.push(posting.visa_sponsorship === "yes" ? "Sponsors visas" : "No visa sponsorship");
  if (posting.years_experience !== null) facts.push(`${posting.years_experience}+ yrs`);
  if (posting.tech_stack.length > 0) facts.push(posting.tech_stack.slice(0, 6).join(", "));
  return facts;
}

/** One gap analysis column: each requirement, what the resume shows for it, and how to talk about it. */
function GapList({ title, items }: { title: string; items: GapItem[] }) {
  return (
    <div>
      <p className="font-medium">
        {title} ({items.length})
      </p>
      <ul className="mt-1 space-y-2">
        {items.map((item) => (
          <li key={item.requirement}>
            <p>{item.requirement}</p>
            {item.evidence && <p className="text-xs text-muted-foreground">Resume: {item.evidence}</p>}
            <p className="text-xs text-muted-foreground">{item.suggestion}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
